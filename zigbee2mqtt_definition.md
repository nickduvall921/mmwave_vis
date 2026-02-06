{
    "description": "mmWave Zigbee Dimmer",
    "exposes": [
        {
            "features": [
                {
                    "access": 7,
                    "description": "On/off state of this light",
                    "label": "State",
                    "name": "state",
                    "property": "state",
                    "type": "binary",
                    "value_off": "OFF",
                    "value_on": "ON",
                    "value_toggle": "TOGGLE"
                },
                {
                    "access": 7,
                    "description": "Brightness of this light",
                    "label": "Brightness",
                    "name": "brightness",
                    "property": "brightness",
                    "type": "numeric",
                    "value_max": 254,
                    "value_min": 0
                }
            ],
            "type": "light"
        },
        {
            "access": 3,
            "category": "config",
            "features": [
                {
                    "access": 3,
                    "description": "Animation Effect to use for the LEDs",
                    "label": "Effect",
                    "name": "effect",
                    "property": "effect",
                    "type": "enum",
                    "values": [
                        "off",
                        "solid",
                        "fast_blink",
                        "slow_blink",
                        "pulse",
                        "chase",
                        "open_close",
                        "small_to_big",
                        "aurora",
                        "slow_falling",
                        "medium_falling",
                        "fast_falling",
                        "slow_rising",
                        "medium_rising",
                        "fast_rising",
                        "medium_blink",
                        "slow_chase",
                        "fast_chase",
                        "fast_siren",
                        "slow_siren",
                        "clear_effect"
                    ]
                },
                {
                    "access": 3,
                    "description": "Calculated by using a hue color circle(value/255*360) If color = 255 display white",
                    "label": "Color",
                    "name": "color",
                    "property": "color",
                    "type": "numeric",
                    "value_max": 255,
                    "value_min": 0
                },
                {
                    "access": 3,
                    "description": "Brightness of the LEDs",
                    "label": "Level",
                    "name": "level",
                    "property": "level",
                    "type": "numeric",
                    "value_max": 100,
                    "value_min": 0
                },
                {
                    "access": 3,
                    "description": "1-60 is in seconds calculated 61-120 is in minutes calculated by(value-60) Example a value of 65 would be 65-60 = 5 minutes - 120-254 Is in hours calculated by(value-120) Example a value of 132 would be 132-120 would be 12 hours. - 255 Indefinitely",
                    "label": "Duration",
                    "name": "duration",
                    "property": "duration",
                    "type": "numeric",
                    "value_max": 255,
                    "value_min": 0
                }
            ],
            "label": "Led effect",
            "name": "led_effect",
            "property": "led_effect",
            "type": "composite"
        },
        {
            "access": 3,
            "category": "config",
            "features": [
                {
                    "access": 3,
                    "description": "Individual LED to target.",
                    "label": "Led",
                    "name": "led",
                    "property": "led",
                    "type": "enum",
                    "values": [
                        "1",
                        "2",
                        "3",
                        "4",
                        "5",
                        "6",
                        "7"
                    ]
                },
                {
                    "access": 3,
                    "description": "Animation Effect to use for the LED",
                    "label": "Effect",
                    "name": "effect",
                    "property": "effect",
                    "type": "enum",
                    "values": [
                        "off",
                        "solid",
                        "fast_blink",
                        "slow_blink",
                        "pulse",
                        "chase",
                        "falling",
                        "rising",
                        "aurora",
                        "clear_effect"
                    ]
                },
                {
                    "access": 3,
                    "description": "Calculated by using a hue color circle(value/255*360) If color = 255 display white",
                    "label": "Color",
                    "name": "color",
                    "property": "color",
                    "type": "numeric",
                    "value_max": 255,
                    "value_min": 0
                },
                {
                    "access": 3,
                    "description": "Brightness of the LED",
                    "label": "Level",
                    "name": "level",
                    "property": "level",
                    "type": "numeric",
                    "value_max": 100,
                    "value_min": 0
                },
                {
                    "access": 3,
                    "description": "1-60 is in seconds calculated 61-120 is in minutes calculated by(value-60) Example a value of 65 would be 65-60 = 5 minutes - 120-254 Is in hours calculated by(value-120)  Example a value of 132 would be 132-120 would be 12 hours. - 255 Indefinitely",
                    "label": "Duration",
                    "name": "duration",
                    "property": "duration",
                    "type": "numeric",
                    "value_max": 255,
                    "value_min": 0
                }
            ],
            "label": "Individual led effect",
            "name": "individual_led_effect",
            "property": "individual_led_effect",
            "type": "composite"
        },
        {
            "access": 1,
            "category": "diagnostic",
            "description": "Indication that a specific notification has completed.",
            "label": "NotificationComplete",
            "name": "notificationComplete",
            "property": "notificationComplete",
            "type": "enum",
            "values": [
                "LED_1",
                "LED_2",
                "LED_3",
                "LED_4",
                "LED_5",
                "LED_6",
                "LED_7",
                "ALL_LEDS",
                "CONFIG_BUTTON_DOUBLE_PRESS"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light dims up when controlled from the hub. A setting of 0 turns the light immediately on. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 25 (2.5s)",
            "label": "DimmingSpeedUpRemote",
            "name": "dimmingSpeedUpRemote",
            "property": "dimmingSpeedUpRemote",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light dims up when controlled at the switch. A setting of 0 turns the light immediately on. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with dimmingSpeedUpRemote setting.",
            "label": "DimmingSpeedUpLocal",
            "name": "dimmingSpeedUpLocal",
            "property": "dimmingSpeedUpLocal",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light turns on when controlled from the hub. A setting of 0 turns the light immediately on. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with dimmingSpeedUpRemote setting.",
            "label": "RampRateOffToOnRemote",
            "name": "rampRateOffToOnRemote",
            "property": "rampRateOffToOnRemote",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light turns on when controlled at the switch. A setting of 0 turns the light immediately on. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with dimmingSpeedUpRemote setting.",
            "label": "RampRateOffToOnLocal",
            "name": "rampRateOffToOnLocal",
            "property": "rampRateOffToOnLocal",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light dims down when controlled from the hub. A setting of 0 turns the light immediately off. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with dimmingSpeedUpRemote setting.",
            "label": "DimmingSpeedDownRemote",
            "name": "dimmingSpeedDownRemote",
            "property": "dimmingSpeedDownRemote",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light dims down when controlled at the switch. A setting of 0 turns the light immediately off. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with dimmingSpeedUpLocal setting.",
            "label": "DimmingSpeedDownLocal",
            "name": "dimmingSpeedDownLocal",
            "property": "dimmingSpeedDownLocal",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light turns off when controlled from the hub. A setting of 'instant' turns the light immediately off. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with rampRateOffToOnRemote setting.",
            "label": "RampRateOnToOffRemote",
            "name": "rampRateOnToOffRemote",
            "property": "rampRateOnToOffRemote",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the speed that the light turns off when controlled at the switch. A setting of 'instant' turns the light immediately off. Increasing the value slows down the transition speed. Every number represents 100ms. Default = 127 - Keep in sync with rampRateOffToOnLocal setting.",
            "label": "RampRateOnToOffLocal",
            "name": "rampRateOnToOffLocal",
            "property": "rampRateOnToOffLocal",
            "type": "numeric",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Inverts the orientation of the switch. Useful when the switch is installed upside down. Essentially up becomes down and down becomes up.",
            "label": "InvertSwitch",
            "name": "invertSwitch",
            "property": "invertSwitch",
            "type": "enum",
            "values": [
                "Yes",
                "No"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Automatically turns the switch off after this many seconds. When the switch is turned on a timer is started. When the timer expires, the switch is turned off. 0 = Auto off is disabled.",
            "label": "AutoTimerOff",
            "name": "autoTimerOff",
            "presets": [
                {
                    "description": "",
                    "name": "Disabled",
                    "value": 0
                }
            ],
            "property": "autoTimerOff",
            "type": "numeric",
            "unit": "seconds",
            "value_max": 32767,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Default level for the load when it is turned on at the switch. A setting of 255 means that the switch will return to the level that it was on before it was turned off.",
            "label": "DefaultLevelLocal",
            "name": "defaultLevelLocal",
            "property": "defaultLevelLocal",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Default level for the load when it is turned on from the hub. A setting of 255 means that the switch will return to the level that it was on before it was turned off.",
            "label": "DefaultLevelRemote",
            "name": "defaultLevelRemote",
            "property": "defaultLevelRemote",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "The state the switch should return to when power is restored after power failure. 0 = off, 1-254 = level, 255 = previous.",
            "label": "StateAfterPowerRestored",
            "name": "stateAfterPowerRestored",
            "property": "stateAfterPowerRestored",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Shows the level that the load is at for x number of seconds after the load is adjusted and then returns to the Default LED state. 0 = Stay Off, 1-10 = seconds, 11 = Stay On.",
            "label": "LoadLevelIndicatorTimeout",
            "name": "loadLevelIndicatorTimeout",
            "property": "loadLevelIndicatorTimeout",
            "type": "enum",
            "values": [
                "Stay Off",
                "1 Second",
                "2 Seconds",
                "3 Seconds",
                "4 Seconds",
                "5 Seconds",
                "6 Seconds",
                "7 Seconds",
                "8 Seconds",
                "9 Seconds",
                "10 Seconds",
                "Stay On"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set the switch configuration.",
            "label": "SwitchType",
            "name": "switchType",
            "property": "switchType",
            "type": "enum",
            "values": [
                "Single Pole",
                "Aux Switch"
            ]
        },
        {
            "access": 5,
            "description": "The temperature measured by the temperature sensor inside the chip, in degrees Celsius",
            "label": "InternalTemperature",
            "name": "internalTemperature",
            "property": "internalTemperature",
            "type": "numeric",
            "unit": "°C",
            "value_max": 127,
            "value_min": 0
        },
        {
            "access": 5,
            "description": "Indicates if the internal chipset is currently in an overheated state.",
            "label": "Overheat",
            "name": "overheat",
            "property": "overheat",
            "type": "enum",
            "values": [
                "No Alert",
                "Overheated"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "This will set the button press delay. 0 = no delay (Disables Button Press Events), Default = 500ms.",
            "label": "ButtonDelay",
            "name": "buttonDelay",
            "property": "buttonDelay",
            "type": "enum",
            "values": [
                "0ms",
                "100ms",
                "200ms",
                "300ms",
                "400ms",
                "500ms",
                "600ms",
                "700ms",
                "800ms",
                "900ms"
            ]
        },
        {
            "access": 5,
            "description": "The number of devices currently bound (excluding gateways) and counts one group as two devices",
            "label": "DeviceBindNumber",
            "name": "deviceBindNumber",
            "property": "deviceBindNumber",
            "type": "numeric"
        },
        {
            "access": 7,
            "category": "config",
            "description": "For use with Smart Bulbs that need constant power and are controlled via commands rather than power.",
            "label": "SmartBulbMode",
            "name": "smartBulbMode",
            "property": "smartBulbMode",
            "type": "enum",
            "values": [
                "Disabled",
                "Smart Bulb Mode"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Enable or Disable setting level to parameter 55 on double-tap UP.",
            "label": "DoubleTapUpToParam55",
            "name": "doubleTapUpToParam55",
            "property": "doubleTapUpToParam55",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Enable or Disable setting level to parameter 56 on double-tap DOWN.",
            "label": "DoubleTapDownToParam56",
            "name": "doubleTapDownToParam56",
            "property": "doubleTapDownToParam56",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set this level on double-tap UP (if enabled by P53). 255 = send ON command.",
            "label": "BrightnessLevelForDoubleTapUp",
            "name": "brightnessLevelForDoubleTapUp",
            "property": "brightnessLevelForDoubleTapUp",
            "type": "numeric",
            "value_max": 255,
            "value_min": 2
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set this level on double-tap DOWN (if enabled by P54). 255 = send OFF command.",
            "label": "BrightnessLevelForDoubleTapDown",
            "name": "brightnessLevelForDoubleTapDown",
            "property": "brightnessLevelForDoubleTapDown",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set the color of the LED Indicator when the load is on.",
            "label": "LedColorWhenOn",
            "name": "ledColorWhenOn",
            "presets": [
                {
                    "description": "",
                    "name": "Red",
                    "value": 0
                },
                {
                    "description": "",
                    "name": "Orange",
                    "value": 21
                },
                {
                    "description": "",
                    "name": "Yellow",
                    "value": 42
                },
                {
                    "description": "",
                    "name": "Green",
                    "value": 85
                },
                {
                    "description": "",
                    "name": "Cyan",
                    "value": 127
                },
                {
                    "description": "",
                    "name": "Blue",
                    "value": 170
                },
                {
                    "description": "",
                    "name": "Violet",
                    "value": 212
                },
                {
                    "description": "",
                    "name": "Pink",
                    "value": 234
                },
                {
                    "description": "",
                    "name": "White",
                    "value": 255
                }
            ],
            "property": "ledColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set the color of the LED Indicator when the load is off.",
            "label": "LedColorWhenOff",
            "name": "ledColorWhenOff",
            "presets": [
                {
                    "description": "",
                    "name": "Red",
                    "value": 0
                },
                {
                    "description": "",
                    "name": "Orange",
                    "value": 21
                },
                {
                    "description": "",
                    "name": "Yellow",
                    "value": 42
                },
                {
                    "description": "",
                    "name": "Green",
                    "value": 85
                },
                {
                    "description": "",
                    "name": "Cyan",
                    "value": 127
                },
                {
                    "description": "",
                    "name": "Blue",
                    "value": 170
                },
                {
                    "description": "",
                    "name": "Violet",
                    "value": 212
                },
                {
                    "description": "",
                    "name": "Pink",
                    "value": 234
                },
                {
                    "description": "",
                    "name": "White",
                    "value": 255
                }
            ],
            "property": "ledColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set the intensity of the LED Indicator when the load is on.",
            "label": "LedIntensityWhenOn",
            "name": "ledIntensityWhenOn",
            "property": "ledIntensityWhenOn",
            "type": "numeric",
            "value_max": 100,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Set the intensity of the LED Indicator when the load is off.",
            "label": "LedIntensityWhenOff",
            "name": "ledIntensityWhenOff",
            "property": "ledIntensityWhenOff",
            "type": "numeric",
            "value_max": 100,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Behavior of single tapping the on or off button. Old behavior turns the switch on or off. New behavior cycles through the levels set by P131-133. Down Always Off is like the new behavior but down always turns the switch off instead of going to next lower speed.",
            "label": "SingleTapBehavior",
            "name": "singleTapBehavior",
            "property": "singleTapBehavior",
            "type": "enum",
            "values": [
                "Old Behavior",
                "New Behavior",
                "Down Always Off"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Which mode to use when binding EP3 (config button) to another device (like a fan module).",
            "label": "FanControlMode",
            "name": "fanControlMode",
            "property": "fanControlMode",
            "type": "enum",
            "values": [
                "Disabled",
                "Multi Tap",
                "Cycle",
                "Toggle"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Level to send to device bound to EP3 when set to low.",
            "label": "LowLevelForFanControlMode",
            "name": "lowLevelForFanControlMode",
            "property": "lowLevelForFanControlMode",
            "type": "numeric",
            "value_max": 254,
            "value_min": 2
        },
        {
            "access": 7,
            "category": "config",
            "description": "Level to send to device bound to EP3 when set to medium.",
            "label": "MediumLevelForFanControlMode",
            "name": "mediumLevelForFanControlMode",
            "property": "mediumLevelForFanControlMode",
            "type": "numeric",
            "value_max": 254,
            "value_min": 2
        },
        {
            "access": 7,
            "category": "config",
            "description": "Level to send to device bound to EP3 when set to high.",
            "label": "HighLevelForFanControlMode",
            "name": "highLevelForFanControlMode",
            "property": "highLevelForFanControlMode",
            "type": "numeric",
            "value_max": 254,
            "value_min": 2
        },
        {
            "access": 7,
            "category": "config",
            "description": "LED color used to display fan control mode.",
            "label": "LedColorForFanControlMode",
            "name": "ledColorForFanControlMode",
            "presets": [
                {
                    "description": "",
                    "name": "Red",
                    "value": 0
                },
                {
                    "description": "",
                    "name": "Orange",
                    "value": 21
                },
                {
                    "description": "",
                    "name": "Yellow",
                    "value": 42
                },
                {
                    "description": "",
                    "name": "Green",
                    "value": 85
                },
                {
                    "description": "",
                    "name": "Cyan",
                    "value": 127
                },
                {
                    "description": "",
                    "name": "Blue",
                    "value": 170
                },
                {
                    "description": "",
                    "name": "Violet",
                    "value": 212
                },
                {
                    "description": "",
                    "name": "Pink",
                    "value": 234
                },
                {
                    "description": "",
                    "name": "White",
                    "value": 255
                }
            ],
            "property": "ledColorForFanControlMode",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Have unique scene numbers for scenes activated with the aux switch.",
            "label": "AuxSwitchUniqueScenes",
            "name": "auxSwitchUniqueScenes",
            "property": "auxSwitchUniqueScenes",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Send Move_To_Level using Default Level with Off/On to bound devices.",
            "label": "BindingOffToOnSyncLevel",
            "name": "bindingOffToOnSyncLevel",
            "property": "bindingOffToOnSyncLevel",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Ability to control switch from the wall.",
            "label": "LocalProtection",
            "name": "localProtection",
            "property": "localProtection",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 5,
            "description": "Ability to control switch from the hub.",
            "label": "RemoteProtection",
            "name": "remoteProtection",
            "property": "remoteProtection",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "When the device is in On/Off mode, use full LED bar or just one LED.",
            "label": "OnOffLedMode",
            "name": "onOffLedMode",
            "property": "onOffLedMode",
            "type": "enum",
            "values": [
                "All",
                "One"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Display progress on LED bar during firmware update.",
            "label": "FirmwareUpdateInProgressIndicator",
            "name": "firmwareUpdateInProgressIndicator",
            "property": "firmwareUpdateInProgressIndicator",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed1ColorWhenOn",
            "name": "defaultLed1ColorWhenOn",
            "property": "defaultLed1ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed1ColorWhenOff",
            "name": "defaultLed1ColorWhenOff",
            "property": "defaultLed1ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed1IntensityWhenOn",
            "name": "defaultLed1IntensityWhenOn",
            "property": "defaultLed1IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed1IntensityWhenOff",
            "name": "defaultLed1IntensityWhenOff",
            "property": "defaultLed1IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed2ColorWhenOn",
            "name": "defaultLed2ColorWhenOn",
            "property": "defaultLed2ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed2ColorWhenOff",
            "name": "defaultLed2ColorWhenOff",
            "property": "defaultLed2ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed2IntensityWhenOn",
            "name": "defaultLed2IntensityWhenOn",
            "property": "defaultLed2IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed2IntensityWhenOff",
            "name": "defaultLed2IntensityWhenOff",
            "property": "defaultLed2IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed3ColorWhenOn",
            "name": "defaultLed3ColorWhenOn",
            "property": "defaultLed3ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed3ColorWhenOff",
            "name": "defaultLed3ColorWhenOff",
            "property": "defaultLed3ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed3IntensityWhenOn",
            "name": "defaultLed3IntensityWhenOn",
            "property": "defaultLed3IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed3IntensityWhenOff",
            "name": "defaultLed3IntensityWhenOff",
            "property": "defaultLed3IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed4ColorWhenOn",
            "name": "defaultLed4ColorWhenOn",
            "property": "defaultLed4ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed4ColorWhenOff",
            "name": "defaultLed4ColorWhenOff",
            "property": "defaultLed4ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed4IntensityWhenOn",
            "name": "defaultLed4IntensityWhenOn",
            "property": "defaultLed4IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed4IntensityWhenOff",
            "name": "defaultLed4IntensityWhenOff",
            "property": "defaultLed4IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed5ColorWhenOn",
            "name": "defaultLed5ColorWhenOn",
            "property": "defaultLed5ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed5ColorWhenOff",
            "name": "defaultLed5ColorWhenOff",
            "property": "defaultLed5ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed5IntensityWhenOn",
            "name": "defaultLed5IntensityWhenOn",
            "property": "defaultLed5IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed5IntensityWhenOff",
            "name": "defaultLed5IntensityWhenOff",
            "property": "defaultLed5IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed6ColorWhenOn",
            "name": "defaultLed6ColorWhenOn",
            "property": "defaultLed6ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed6ColorWhenOff",
            "name": "defaultLed6ColorWhenOff",
            "property": "defaultLed6ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed6IntensityWhenOn",
            "name": "defaultLed6IntensityWhenOn",
            "property": "defaultLed6IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed6IntensityWhenOff",
            "name": "defaultLed6IntensityWhenOff",
            "property": "defaultLed6IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed7ColorWhenOn",
            "name": "defaultLed7ColorWhenOn",
            "property": "defaultLed7ColorWhenOn",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "0-254:This is the color of the LED strip in a hex representation. 255:Synchronization with default all LED strip color parameter.",
            "label": "DefaultLed7ColorWhenOff",
            "name": "defaultLed7ColorWhenOff",
            "property": "defaultLed7ColorWhenOff",
            "type": "numeric",
            "value_max": 255,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when on. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed7IntensityWhenOn",
            "name": "defaultLed7IntensityWhenOn",
            "property": "defaultLed7IntensityWhenOn",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Intensity of LED strip when off. 101 = Synchronized with default all LED strip intensity parameter.",
            "label": "DefaultLed7IntensityWhenOff",
            "name": "defaultLed7IntensityWhenOff",
            "property": "defaultLed7IntensityWhenOff",
            "type": "numeric",
            "value_max": 101,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Enable or disable advanced timer mode to have the switch act like a bathroom fan timer",
            "label": "FanTimerMode",
            "name": "fanTimerMode",
            "property": "fanTimerMode",
            "type": "enum",
            "values": [
                "Disabled",
                "Enabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Double-Tap the Config button to clear notifications.",
            "label": "DoubleTapClearNotifications",
            "name": "doubleTapClearNotifications",
            "property": "doubleTapClearNotifications",
            "type": "enum",
            "values": [
                "Enabled (Default)",
                "Disabled"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Level display of the LED Strip",
            "label": "FanLedLevelType",
            "name": "fanLedLevelType",
            "presets": [
                {
                    "description": "",
                    "name": "Limitless (like VZM31)",
                    "value": 0
                },
                {
                    "description": "",
                    "name": "Adaptive LED",
                    "value": 10
                }
            ],
            "property": "fanLedLevelType",
            "type": "numeric",
            "value_max": 10,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "The minimum level that the dimmer allows the bulb to be dimmed to. Useful when the user has an LED bulb that does not turn on or flickers at a lower level.",
            "label": "MinimumLevel",
            "name": "minimumLevel",
            "property": "minimumLevel",
            "type": "numeric",
            "value_max": 254,
            "value_min": 1
        },
        {
            "access": 7,
            "category": "config",
            "description": "The maximum level that the dimmer allows the bulb to be dimmed to.Useful when the user has an LED bulb that reaches its maximum level before the dimmer value of 99 or when the user wants to limit the maximum brightness.",
            "label": "MaximumLevel",
            "name": "maximumLevel",
            "property": "maximumLevel",
            "type": "numeric",
            "value_max": 255,
            "value_min": 2
        },
        {
            "access": 5,
            "description": "Set the power type for the device.",
            "label": "PowerType",
            "name": "powerType",
            "property": "powerType",
            "type": "enum",
            "values": [
                "Non Neutral",
                "Neutral"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Use device as a Dimmer or an On/Off switch.",
            "label": "OutputMode",
            "name": "outputMode",
            "property": "outputMode",
            "type": "enum",
            "values": [
                "Dimmer",
                "On/Off"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Method used for scaling.",
            "label": "LedBarScaling",
            "name": "ledBarScaling",
            "property": "ledBarScaling",
            "type": "enum",
            "values": [
                "Gen3 method (VZM-style)",
                "Gen2 method (LZW-style)"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Percent power level change that will result in a new power report being sent. 0 = Disabled",
            "label": "ActivePowerReports",
            "name": "activePowerReports",
            "property": "activePowerReports",
            "type": "numeric",
            "value_max": 100,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Time period between consecutive power & energy reports being sent (in seconds). The timer is reset after each report is sent.",
            "label": "PeriodicPowerAndEnergyReports",
            "name": "periodicPowerAndEnergyReports",
            "property": "periodicPowerAndEnergyReports",
            "type": "numeric",
            "value_max": 32767,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Energy reports Energy level change which will result in sending a new energy report.0 = disabled, 1-32767 = 0.01kWh-327.67kWh. Default setting: 10 (0.1 kWh)",
            "label": "ActiveEnergyReports",
            "name": "activeEnergyReports",
            "property": "activeEnergyReports",
            "type": "numeric",
            "value_max": 32767,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Duration of full power output while lamp transitions from Off to On. In 60th of second. 0 = disable, 1 = 1/60s, 60 = 1s",
            "label": "QuickStartTime",
            "name": "quickStartTime",
            "property": "quickStartTime",
            "type": "numeric",
            "value_max": 60,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Level of power output during Quick Start Light time (P23).",
            "label": "QuickStartLevel",
            "name": "quickStartLevel",
            "property": "quickStartLevel",
            "type": "numeric",
            "value_max": 254,
            "value_min": 1
        },
        {
            "access": 7,
            "category": "config",
            "description": "Increase level in non-neutral mode",
            "label": "HigherOutputInNonNeutral",
            "name": "higherOutputInNonNeutral",
            "property": "higherOutputInNonNeutral",
            "type": "enum",
            "values": [
                "Disabled (default)",
                "Enabled"
            ]
        },
        {
            "access": 5,
            "description": "Switches the dimming mode from leading edge (default) to trailing edge. 1. Trailing Edge is only available on neutral single-pole and neutral multi-way with an aux/add-on switch (multi-way with a dumb/existing switch and non-neutral setups are not supported and will default back to Leading Edge). This parameter can only be changed at the switch.",
            "label": "DimmingMode",
            "name": "dimmingMode",
            "property": "dimmingMode",
            "type": "enum",
            "values": [
                "Leading edge",
                "Trailing edge"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Which endpoint should the switch advertise for OTA update (Zigbee, mmWave, or both).",
            "label": "OtaImageType",
            "name": "otaImageType",
            "property": "otaImageType",
            "type": "enum",
            "values": [
                "Zigbee (259)",
                "mmWave (260)",
                "Alternating (259 & 260) (default)"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Controls whether the wired load is automatically turned on / off by the presence detector. 0 = Disabled (manual control of the load), 1 = Occupancy (default; turn on automatically with presence; turn off automatically without presence), 2 = Vacancy (does not turn on automatically; turn off automatically without presence), 3 = Wasteful Occupancy (turn on automatically with presence; does not turn off automatically), 4 = Mirrored Occupancy (turn on automatically without presence; turn off automatically with presence), 5 = Mirrored Vacancy (turn on automatically without presence; does not turn off automatically), 6 = Mirrored Wasteful Occupancy (does not turn on automatically; turns off automatically with presence).",
            "label": "MmwaveControlWiredDevice",
            "name": "mmwaveControlWiredDevice",
            "property": "mmwaveControlWiredDevice",
            "type": "enum",
            "values": [
                "Disabled",
                "Occupancy (default)",
                "Vacancy",
                "Wasteful Occupancy",
                "Mirrored Occupancy",
                "Mirrored Vacancy",
                "Mirrored Wasteful Occupancy"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Allows selection of predefined room dimensions for mmWave sensor processing. Useful for optimizing detection zones based on installation environment. Defaults to Custom which allows for manual dimension configuration via other parameters. \nOptions: 0=Custom (User-defined), 1=Small (X: −100 to 100, Y: 0 to 200, Z: −100 to 100), 2=Medium (X: −160 to 160, Y: 0 to 280, Z: −100 to 100), 3=Large (X: −210 to 210, Y: 0 to 360, Z: −100 to 100)",
            "label": "MmWaveRoomSizePreset",
            "name": "mmWaveRoomSizePreset",
            "property": "mmWaveRoomSizePreset",
            "type": "enum",
            "values": [
                "Custom",
                "Small",
                "Medium",
                "Large"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "This changes the duration, measured in seconds, after the mmWave radar detects transition from the presence of a person to their absence. Default = 10 (seconds).",
            "label": "MmWaveHoldTime",
            "name": "mmWaveHoldTime",
            "property": "mmWaveHoldTime",
            "type": "numeric",
            "value_max": 4294967295,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "The sensitivity of the mmWave sensor.",
            "label": "MmWaveDetectSensitivity",
            "name": "mmWaveDetectSensitivity",
            "property": "mmWaveDetectSensitivity",
            "type": "enum",
            "values": [
                "Low",
                "Medium",
                "High (default)"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "The time from detecting a person to triggering an action.",
            "label": "MmWaveDetectTrigger",
            "name": "mmWaveDetectTrigger",
            "property": "mmWaveDetectTrigger",
            "type": "enum",
            "values": [
                "Slow (5s)",
                "Medium (1s)",
                "Fast (0.2s, default)"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "Send target info report when bound to mmWave cluster.",
            "label": "MmWaveTargetInfoReport",
            "name": "mmWaveTargetInfoReport",
            "property": "mmWaveTargetInfoReport",
            "type": "enum",
            "values": [
                "Disable (default)",
                "Enable"
            ]
        },
        {
            "access": 7,
            "category": "config",
            "description": "The delay time of the stay area is set to 50ms when it is set to 1, to 1 second when it is set to 20, and the default value is 300, that is, 15 seconds",
            "label": "MmWaveStayLife",
            "name": "mmWaveStayLife",
            "property": "mmWaveStayLife",
            "type": "numeric",
            "value_max": 4294967295,
            "value_min": 0
        },
        {
            "access": 5,
            "description": "The firmware version number of the mmWave module.",
            "label": "MmWaveVersion",
            "name": "mmWaveVersion",
            "property": "mmWaveVersion",
            "type": "numeric",
            "value_max": 4294967295,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Defines the detection area (negative values are below the switch, positive values are above)",
            "label": "MmWaveHeightMin",
            "name": "mmWaveHeightMin",
            "property": "mmWaveHeightMin",
            "type": "numeric",
            "value_max": 600,
            "value_min": -600
        },
        {
            "access": 7,
            "category": "config",
            "description": "Defines the detection area (negative values are below the switch, positive values are above)",
            "label": "MmWaveHeightMax",
            "name": "mmWaveHeightMax",
            "property": "mmWaveHeightMax",
            "type": "numeric",
            "value_max": 600,
            "value_min": -600
        },
        {
            "access": 7,
            "category": "config",
            "description": "Defines the detection area (negative values are left of the switch facing away from the wall, positive values are right)",
            "label": "MmWaveWidthMin",
            "name": "mmWaveWidthMin",
            "property": "mmWaveWidthMin",
            "type": "numeric",
            "value_max": 600,
            "value_min": -600
        },
        {
            "access": 7,
            "category": "config",
            "description": "Defines the detection area (negative values are left of the switch facing away from the wall, positive values are right)",
            "label": "MmWaveWidthMax",
            "name": "mmWaveWidthMax",
            "property": "mmWaveWidthMax",
            "type": "numeric",
            "value_max": 600,
            "value_min": -600
        },
        {
            "access": 7,
            "category": "config",
            "description": "Defines the detection area in front of the switch",
            "label": "MmWaveDepthMin",
            "name": "mmWaveDepthMin",
            "property": "mmWaveDepthMin",
            "type": "numeric",
            "value_max": 600,
            "value_min": 0
        },
        {
            "access": 7,
            "category": "config",
            "description": "Defines the detection area in front of the switch",
            "label": "MmWaveDepthMax",
            "name": "mmWaveDepthMax",
            "property": "mmWaveDepthMax",
            "type": "numeric",
            "value_max": 600,
            "value_min": 0
        },
        {
            "access": 3,
            "category": "config",
            "features": [
                {
                    "access": 3,
                    "description": "Which mmWave Control command to send",
                    "label": "ControlID",
                    "name": "controlID",
                    "property": "controlID",
                    "type": "enum",
                    "values": [
                        "reset_mmwave_module",
                        "set_interference",
                        "query_areas",
                        "clear_interference",
                        "reset_detection_area",
                        "clear_stay_areas"
                    ]
                }
            ],
            "label": "Mmwave control commands",
            "name": "mmwave_control_commands",
            "property": "mmwave_control_commands",
            "type": "composite"
        },
        {
            "access": 1,
            "description": "Indicates whether the device detected occupancy in Area 1",
            "label": "Area1Occupancy",
            "name": "area1Occupancy",
            "property": "mmwave_area1_occupancy",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 1,
            "description": "Indicates whether the device detected occupancy in Area 2",
            "label": "Area2Occupancy",
            "name": "area2Occupancy",
            "property": "mmwave_area2_occupancy",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 1,
            "description": "Indicates whether the device detected occupancy in Area 3",
            "label": "Area3Occupancy",
            "name": "area3Occupancy",
            "property": "mmwave_area3_occupancy",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 1,
            "description": "Indicates whether the device detected occupancy in Area 4",
            "label": "Area4Occupancy",
            "name": "area4Occupancy",
            "property": "mmwave_area4_occupancy",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 3,
            "category": "config",
            "description": "Manually defines the coordinates of an interference area, which is an ignored zone where targets are not reported as present. Up to four zones can be defined.",
            "features": [
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 1",
                    "name": "area_1",
                    "property": "area1",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 2",
                    "name": "area_2",
                    "property": "area2",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 3",
                    "name": "area_3",
                    "property": "area3",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 4",
                    "name": "area_4",
                    "property": "area4",
                    "type": "composite"
                }
            ],
            "label": "Mmwave interference areas",
            "name": "mmwave_interference_areas",
            "property": "mmwave_interference_areas",
            "type": "composite"
        },
        {
            "access": 3,
            "category": "config",
            "description": "Defines one or more active detection zones where the sensor reports movement or occupancy. Up to four detection zones can be set.",
            "features": [
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 1",
                    "name": "area_1",
                    "property": "area1",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 2",
                    "name": "area_2",
                    "property": "area2",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 3",
                    "name": "area_3",
                    "property": "area3",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 4",
                    "name": "area_4",
                    "property": "area4",
                    "type": "composite"
                }
            ],
            "label": "Mmwave detection areas",
            "name": "mmwave_detection_areas",
            "property": "mmwave_detection_areas",
            "type": "composite"
        },
        {
            "access": 3,
            "category": "config",
            "description": "Defines one or more stay areas where stationary presence should still be detected. Up to four stay zones can be configured.",
            "features": [
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 1",
                    "name": "area_1",
                    "property": "area1",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 2",
                    "name": "area_2",
                    "property": "area2",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 3",
                    "name": "area_3",
                    "property": "area3",
                    "type": "composite"
                },
                {
                    "access": 1,
                    "features": [
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width min",
                            "name": "width_min",
                            "property": "width_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are left of the switch facing away from the wall, positive values are right)",
                            "label": "Width max",
                            "name": "width_max",
                            "property": "width_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height min",
                            "name": "height_min",
                            "property": "height_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area (negative values are below the switch, positive values are above)",
                            "label": "Height max",
                            "name": "height_max",
                            "property": "height_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": -600
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth min",
                            "name": "depth_min",
                            "property": "depth_min",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        },
                        {
                            "access": 3,
                            "description": "Defines the area in front of the switch",
                            "label": "Depth max",
                            "name": "depth_max",
                            "property": "depth_max",
                            "type": "numeric",
                            "value_max": 600,
                            "value_min": 0
                        }
                    ],
                    "label": "Area 4",
                    "name": "area_4",
                    "property": "area4",
                    "type": "composite"
                }
            ],
            "label": "Mmwave stay areas",
            "name": "mmwave_stay_areas",
            "property": "mmwave_stay_areas",
            "type": "composite"
        },
        {
            "access": 2,
            "category": "config",
            "description": "Initiate device identification",
            "label": "Identify",
            "name": "identify",
            "property": "identify",
            "type": "enum",
            "values": [
                "identify"
            ]
        },
        {
            "access": 2,
            "category": "config",
            "description": "Reset energy meter",
            "label": "Energy reset",
            "name": "energy_reset",
            "property": "energy_reset",
            "type": "enum",
            "values": [
                "reset"
            ]
        },
        {
            "access": 5,
            "description": "Instantaneous measured power",
            "label": "Power",
            "name": "power",
            "property": "power",
            "type": "numeric",
            "unit": "W"
        },
        {
            "access": 5,
            "description": "Measured electrical potential value",
            "label": "Voltage",
            "name": "voltage",
            "property": "voltage",
            "type": "numeric",
            "unit": "V"
        },
        {
            "access": 5,
            "description": "Instantaneous measured electrical current",
            "label": "Current",
            "name": "current",
            "property": "current",
            "type": "numeric",
            "unit": "A"
        },
        {
            "access": 5,
            "description": "Sum of consumed energy",
            "label": "Energy",
            "name": "energy",
            "property": "energy",
            "type": "numeric",
            "unit": "kWh"
        },
        {
            "access": 5,
            "description": "Measured illuminance",
            "label": "Illuminance",
            "name": "illuminance",
            "property": "illuminance",
            "type": "numeric",
            "unit": "lx"
        },
        {
            "access": 5,
            "description": "Indicates whether the device detected occupancy",
            "label": "Occupancy",
            "name": "occupancy",
            "property": "occupancy",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 1,
            "category": "diagnostic",
            "description": "Triggered action (e.g. a button click)",
            "label": "Action",
            "name": "action",
            "property": "action",
            "type": "enum",
            "values": [
                "down_single",
                "up_single",
                "config_single",
                "down_release",
                "up_release",
                "config_release",
                "down_held",
                "up_held",
                "config_held",
                "down_double",
                "up_double",
                "config_double",
                "down_triple",
                "up_triple",
                "config_triple",
                "down_quadruple",
                "up_quadruple",
                "config_quadruple",
                "down_quintuple",
                "up_quintuple",
                "config_quintuple"
            ]
        },
        {
            "access": 1,
            "category": "diagnostic",
            "description": "Link quality (signal strength)",
            "label": "Linkquality",
            "name": "linkquality",
            "property": "linkquality",
            "type": "numeric",
            "unit": "lqi",
            "value_max": 255,
            "value_min": 0
        }
    ],
    "model": "VZM32-SN",
    "options": [
        {
            "access": 2,
            "description": "Calibrates the power value (percentual offset), takes into effect on next report of device.",
            "label": "Power calibration",
            "name": "power_calibration",
            "property": "power_calibration",
            "type": "numeric",
            "value_step": 0.1
        },
        {
            "access": 2,
            "description": "Number of digits after decimal point for power, takes into effect on next report of device. This option can only decrease the precision, not increase it.",
            "label": "Power precision",
            "name": "power_precision",
            "property": "power_precision",
            "type": "numeric",
            "value_max": 3,
            "value_min": 0
        },
        {
            "access": 2,
            "description": "Calibrates the voltage value (percentual offset), takes into effect on next report of device.",
            "label": "Voltage calibration",
            "name": "voltage_calibration",
            "property": "voltage_calibration",
            "type": "numeric",
            "value_step": 0.1
        },
        {
            "access": 2,
            "description": "Number of digits after decimal point for voltage, takes into effect on next report of device. This option can only decrease the precision, not increase it.",
            "label": "Voltage precision",
            "name": "voltage_precision",
            "property": "voltage_precision",
            "type": "numeric",
            "value_max": 3,
            "value_min": 0
        },
        {
            "access": 2,
            "description": "Calibrates the current value (percentual offset), takes into effect on next report of device.",
            "label": "Current calibration",
            "name": "current_calibration",
            "property": "current_calibration",
            "type": "numeric",
            "value_step": 0.1
        },
        {
            "access": 2,
            "description": "Number of digits after decimal point for current, takes into effect on next report of device. This option can only decrease the precision, not increase it.",
            "label": "Current precision",
            "name": "current_precision",
            "property": "current_precision",
            "type": "numeric",
            "value_max": 3,
            "value_min": 0
        },
        {
            "access": 2,
            "description": "Calibrates the energy value (percentual offset), takes into effect on next report of device.",
            "label": "Energy calibration",
            "name": "energy_calibration",
            "property": "energy_calibration",
            "type": "numeric",
            "value_step": 0.1
        },
        {
            "access": 2,
            "description": "Number of digits after decimal point for energy, takes into effect on next report of device. This option can only decrease the precision, not increase it.",
            "label": "Energy precision",
            "name": "energy_precision",
            "property": "energy_precision",
            "type": "numeric",
            "value_max": 3,
            "value_min": 0
        },
        {
            "access": 2,
            "description": "Calibrates the illuminance value (percentual offset), takes into effect on next report of device.",
            "label": "Illuminance calibration",
            "name": "illuminance_calibration",
            "property": "illuminance_calibration",
            "type": "numeric",
            "value_step": 0.1
        },
        {
            "access": 2,
            "description": "Controls the transition time (in seconds) of on/off, brightness, color temperature (if applicable) and color (if applicable) changes. Defaults to `0` (no transition).",
            "label": "Transition",
            "name": "transition",
            "property": "transition",
            "type": "numeric",
            "value_min": 0,
            "value_step": 0.1
        },
        {
            "access": 2,
            "description": "Sets the duration of the identification procedure in seconds (i.e., how long the device would flash).The value ranges from 1 to 30 seconds (default: 3).",
            "label": "Identify timeout",
            "name": "identify_timeout",
            "property": "identify_timeout",
            "type": "numeric",
            "value_max": 30,
            "value_min": 1
        },
        {
            "access": 2,
            "description": "State actions will also be published as 'action' when true (default false).",
            "label": "State action",
            "name": "state_action",
            "property": "state_action",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 2,
            "description": "Expose the raw illuminance value.",
            "label": "Illuminance raw",
            "name": "illuminance_raw",
            "property": "illuminance_raw",
            "type": "binary",
            "value_off": false,
            "value_on": true
        },
        {
            "access": 2,
            "description": "Sends a message after the last time no occupancy (occupancy: false) was detected. When setting this for example to [10, 60] a `{\"no_occupancy_since\": 10}` will be sent after 10 seconds and a `{\"no_occupancy_since\": 60}` after 60 seconds.",
            "item_type": {
                "access": 3,
                "label": "Time",
                "name": "time",
                "type": "numeric"
            },
            "label": "No occupancy since",
            "name": "no_occupancy_since",
            "property": "no_occupancy_since",
            "type": "list"
        }
    ],
    "source": "native",
    "supports_ota": true,
    "vendor": "Inovelli"
}