import network
import espnow
import machine
import time
import random

# --- Configurations ---
TOUCH_PINS = [4]
NUM_CHANNELS = len(TOUCH_PINS)

# Lower threshold to prevent noise from keeping the pin permanently "pressed"
TOUCH_THRESHOLD = 150 

ONBOARD_LED_PIN = 2
onboard_led = machine.Pin(ONBOARD_LED_PIN, machine.Pin.OUT)
onboard_led.value(0)

active_channel = None 
last_on_time_ms = 0  # Timestamp guard to suppress delayed CLEAR_OTHERS

# --- Initialize Touch Hardware ---
touch_pads = []
for pin in TOUCH_PINS:
    try:
        touch_pads.append(machine.TouchPad(machine.Pin(pin)))
    except Exception as err:
        print(f"Warning initializing TouchPad on Pin {pin}: {err}")

# --- ESP-NOW Setup ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.disconnect() 

e = espnow.ESPNow()
e.active(True)

BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
try:
    e.add_peer(BROADCAST_MAC)
except OSError:
    pass

master_peer_lists = [[] for _ in range(NUM_CHANNELS)]

is_pairing_mode = [False] * NUM_CHANNELS
last_blink_times = [0] * NUM_CHANNELS

touch_was_pressed = [False] * NUM_CHANNELS
touch_press_starts = [0] * NUM_CHANNELS
pairing_live_triggered = [False] * NUM_CHANNELS  

def set_led_state(is_on):
    onboard_led.value(1 if is_on else 0)

def double_flash():
    set_led_state(False)
    for _ in range(2):
        set_led_state(True)
        time.sleep(0.15)
        set_led_state(False)
        time.sleep(0.15)

def register_peer(mac_addr):
    try:
        e.add_peer(mac_addr)
    except OSError:
        pass

def broadcast_to_channel_peers(ch_idx, command_str, exclude_mac=None):
    """Sends a command to every paired device on a specific channel, optionally skipping one MAC."""
    for peer in master_peer_lists[ch_idx]:
        if exclude_mac and peer == exclude_mac:
            continue
        try:
            e.send(peer, f"{command_str}:{ch_idx}".encode('utf-8'))
        except Exception as err:
            print(f"Error sending {command_str} to peer: {err}")

def add_and_sync_peer(ch_idx, new_mac):
    if new_mac not in master_peer_lists[ch_idx]:
        master_peer_lists[ch_idx].append(new_mac)
        register_peer(new_mac)
        print(f"Channel {ch_idx}: Registered peer {new_mac.hex()} (Total peers: {len(master_peer_lists[ch_idx])})")
        return True
    return False

def check_messages():
    global active_channel, last_on_time_ms
    try:
        host, msg = e.recv(0)
    except Exception:
        return

    if msg:
        try:
            msg_str = msg.decode('utf-8')
            
            # Handle MAC sync
            if msg_str.startswith("SHARE_PEER:"):
                parts = msg_str.split(':')
                ch_idx = int(parts[1])
                new_mac = bytes.fromhex(parts[2])
                add_and_sync_peer(ch_idx, new_mac)
                return

            command, channel_str = msg_str.split(':')
            ch_idx = int(channel_str)
            
            if 0 <= ch_idx < NUM_CHANNELS:
                if command == "JOIN_REG" and is_pairing_mode[ch_idx]:
                    add_and_sync_peer(ch_idx, host)
                    
                    for existing_peer in list(master_peer_lists[ch_idx]):
                        if existing_peer != host:
                            try:
                                e.send(existing_peer, f"SHARE_PEER:{ch_idx}:{host.hex()}".encode('utf-8'))
                            except Exception:
                                pass
                                
                    e.send(host, f"CONFIRM:{ch_idx}".encode('utf-8'))
                    for peer in master_peer_lists[ch_idx]:
                        if peer != host:
                            try:
                                e.send(host, f"SHARE_PEER:{ch_idx}:{peer.hex()}".encode('utf-8'))
                            except Exception:
                                pass
                    
                    print(f"Channel {ch_idx}: Fully paired with new board!")

                elif command == "CONFIRM":
                    add_and_sync_peer(ch_idx, host)
                    print(f"Channel {ch_idx}: Pairing confirmed with open session!")
                    double_flash()

                elif command == "ON":
                    print(f"Received turn-on target for Channel {ch_idx}")
                    active_channel = ch_idx
                    last_on_time_ms = time.ticks_ms()
                    set_led_state(True)

                elif command == "CLEAR_OTHERS":
                    # Ignore CLEAR_OTHERS if we turned ON less than 300ms ago
                    if time.ticks_diff(time.ticks_ms(), last_on_time_ms) < 300:
                        return
                    
                    active_channel = None
                    set_led_state(False)

        except Exception as err:
            print(f"Msg Parse Error: {err}")

def run():
    global active_channel
    print(f"=== ESP32 Node Online ===")
    print(f"Monitoring Touch Pins: {TOUCH_PINS}")

    while True:
        now_ms = time.ticks_ms()
        check_messages()
        
        # Flash onboard LED if pairing session is OPEN
        for i in range(NUM_CHANNELS):
            if is_pairing_mode[i]:
                if time.ticks_diff(now_ms, last_blink_times[i]) > 250:
                    onboard_led.value(not onboard_led.value())
                    last_blink_times[i] = now_ms

        # Scan touch header pins
        for i in range(NUM_CHANNELS):
            try:
                touch_val = touch_pads[i].read()
                is_pressed = (touch_val < TOUCH_THRESHOLD)
            except Exception:
                is_pressed = False
            
            if is_pressed:
                if not touch_was_pressed[i]:
                    touch_press_starts[i] = now_ms
                    touch_was_pressed[i] = True
                    pairing_live_triggered[i] = False
                
                # --- HOLD 3 SECONDS FOR PAIRING ---
                hold_duration_ms = time.ticks_diff(now_ms, touch_press_starts[i])
                if hold_duration_ms >= 3000 and not pairing_live_triggered[i]:
                    if not is_pairing_mode[i]:
                        is_pairing_mode[i] = True
                        print(f"Pairing OPEN for Channel {i}...")
                    else:
                        is_pairing_mode[i] = False
                        set_led_state(False)
                        print(f"Pairing CLOSED for Channel {i}.")
                    pairing_live_triggered[i] = True
                    
            else:
                if touch_was_pressed[i]:
                    hold_duration_ms = time.ticks_diff(now_ms, touch_press_starts[i])
                    touch_was_pressed[i] = False
                    
                    if pairing_live_triggered[i]:
                        pairing_live_triggered[i] = False
                        time.sleep(0.15)
                        continue
                    
                    # --- SHORT TOUCH ACTIONS ---
                    if is_pairing_mode[i]:
                        is_pairing_mode[i] = False
                        set_led_state(False)
                        print(f"Pairing CLOSED for Channel {i}.")
                    else:
                        # Broadcast join request to any open pairing sessions
                        try:
                            e.send(BROADCAST_MAC, f"JOIN_REG:{i}".encode('utf-8'))
                        except OSError:
                            pass
                        
                        new_state = (active_channel != i)
                        
                        if new_state:
                            broadcast_to_channel_peers(i, "CLEAR_OTHERS")
                            active_channel = i
                            set_led_state(True)
                            print(f"Toggled Channel {i} ON.")
                        else:
                            active_channel = None
                            set_led_state(False)
                            
                            if len(master_peer_lists[i]) > 0:
                                random_peer = random.choice(master_peer_lists[i])
                                
                                # Clear all peers EXCEPT the target peer to prevent race conditions
                                broadcast_to_channel_peers(i, "CLEAR_OTHERS", exclude_mac=random_peer)
                                
                                try:
                                    e.send(random_peer, f"ON:{i}".encode('utf-8'))
                                    print(f"Transferring token to random peer: {random_peer.hex()}")
                                except Exception as err:
                                    print(f"Send failed: {err}")
                            else:
                                print(f"No paired devices on Channel {i}.")
                                
                    time.sleep(0.15)
                    
        time.sleep(0.01)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nProgram stopped.")
    except Exception as err:
        print(f"Fatal error in main: {err}")