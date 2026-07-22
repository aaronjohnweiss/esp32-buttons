# boot.py
import gc
import esp

# Disable raw OS/vendor debug spam on serial boot
esp.osdebug(None)

# Run garbage collection right away to maximize clean RAM heap
gc.collect()

print("Boot sequence complete. Transitioning to main.py...")