import json

# Run this file to generate the JSON file loaded in main to
# populate the UI dropdowns.

# Tuple is (dstat_code, gain) where dstat_code
# is sent to the dstat over serial, and the gain
# is used during conversion from adc units to amps
DSTAT_GAIN = { "Bypass"            : ("0",1),
               "100 Ohm (15mA FS)" : ("1",100),
               "3 kOhm (500 uA FS)": ("2",3000),
               "30 kOhm (50 uA FS)": ("3",30000),
               "300 kOhm (5 uA FS)": ("4",300000),
               "3 MOhm (500 nA FS)": ("5",3000000),
               "30 MOhm (50 nA FS)": ("6",30000000),
               "100 MOhm (5 nA FS)": ("7",100000000) }

DSTAT_SRATE = { "2.5 Hz":   "3",
                "5 Hz":     "13",
                "10 Hz":    "23",
                "15 Hz":    "33",
                "25 Hz":    "43",
                "30 Hz":    "53",
                "50 Hz":    "63",
                "60 Hz":    "72",
                "100 Hz":   "82",
                "500 Hz":   "92",
                "1 kHz":    "A1",
                "2 kHz":    "B0",
                "3.75 kHz": "C0",
                "7.5 kHz":  "D0",
                "15 kHz":   "E0",
                "30 kHz":   "F0" }

DSTAT_PGA = { "1x":  "1",
              "2x":  "2",
              "4x":  "3",
              "8x":  "4",
              "16x": "5",
              "32x": "6",
              "64x": "7" }

DSTAT_BUFF = { "Enabled":  "1",
               "Disabled": "0" }

# Note: DStat is capable of much more
DSTAT_EXP  = { "Potentiometry":  "P",
               "Linear Sweep Voltammetry": "L" } 

options = { "GAIN": DSTAT_GAIN,
            "SRATE": DSTAT_SRATE,
            "PGA": DSTAT_PGA,
            "BUFF": DSTAT_BUFF,
            "EXP": DSTAT_EXP }

with open("dstat_options.json", 'w') as outfile:
    json.dump(options, outfile, indent=4)
