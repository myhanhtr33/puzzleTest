# SnakeTest project instructions

## Python and tests

- Use `C:\Users\ADMIN\miniconda3_new\envs\airtest310\python.exe` as the default Python interpreter for this project. It contains the project's Airtest, Poco, and pytest dependencies.
- Do not use the project `.venv` or the system `python` for test runs unless the user explicitly requests a different interpreter.
- Run pytest from `F:\SnakeTest` with:

  ```powershell
  & "C:\Users\ADMIN\miniconda3_new\envs\airtest310\python.exe" -m pytest <test paths>
  ```

- Prefer offline tests by default. Real-device tests require a valid connected device/window and should only be run when requested or when the task explicitly requires device verification.
