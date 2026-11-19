# Boot straight into Sparrow instead of the Badgeware app menu.
# Copy over /system/main.py on the badge, keeping Pimoroni's original as main.py.orig.
# To get the app menu back, put the badge in disk mode (tap RESET twice) and restore
# main.py.orig. (Don't hold HOME while resetting: HOME is also BOOT and enters the bootloader.)

# Eat the wakeup button press so it doesn't leak into the app
badge.poll()

app_to_launch = "/system/apps/sparrow"
try:
    launch(app_to_launch)
finally:
    # Catch any exit and reset back into Sparrow
    reset()
