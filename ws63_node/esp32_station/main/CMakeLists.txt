idf_component_register(SRCS "station.c" INCLUDE_DIRS "."
                       PRIV_REQUIRES esp_driver_gpio esp_driver_rmt esp_driver_usb_serial_jtag)
