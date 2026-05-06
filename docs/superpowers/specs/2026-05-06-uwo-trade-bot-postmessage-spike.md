# UWO PostMessage Feasibility Spike — Report

- Date run: TBD (user fills after running the spike)
- Client: UWO 中文私服, build/version TBD
- OS: Windows TBD, DPI TBD
- Spike script: `scripts/spike_postmessage.py`

## Results

| Target | WM_KEYDOWN/UP | WM_LBUTTONDOWN/UP |
|---|---|---|
| Notepad | TBD | n/a |
| UWO client | TBD | TBD |

Notes: TBD (record any quirks: focus stealing, partial keypress recognition, anti-cheat warnings, etc.)

## Conclusion

The user must select one option below after running the spike and delete the others:

- **A. PostMessage works against UWO** → M3 input layer uses `PostMessageBackend` as default. Proceed with the design as written.
- **B. PostMessage does not work, but SendInput in foreground does** → M3 default backend becomes `SendInputBackend`; debug panel shows a "will take over keyboard/mouse" warning; emergency-stop hotkey becomes mandatory.
- **C. Neither works (likely DirectInput / RawInput / anti-tamper)** → Pause input layer scope. M3 ships only `Backend` ABC + `LoopbackBackend`; document hardware HID as the future path.

Selected: TBD
