# Pipecat + Picovoice Porcupine

### Get Started

- Fill out `.env` with the required environment variables for OpenAI (if needed), Picovoice, Elevenlabs, and Deepgram
- Create a virtualenv `python3 -m venv pvcat && source pvcat/bin/activate` and install required libraries `pip install -r requirements.txt`
- Get the needed .ppn files from [Picovoice Developer Console](https://console.picovoice.ai/) and place them in `keyword_files/` directory or any other
- Direct the wake word filter to the keyword files depending on your OS in `utils/pipe.py`: <br>
  `pico_wake_word = CustomWakeCheckFilter(20, user_id, keyword_path_mac="keyword_files/hey_pipe_mac.ppn")`

- Run `main.py` and navigate to `http://localhost:8000` to test


### Things to Note
- Main changes are commented in the `custom_classes/` directory
- A UserId has to be passed to the main pipeline (called from `main.py`) due to AudioRawFrame not having userId as an attribute
- The server and protobuf config being run is provided from the [example provided](https://github.com/pipecat-ai/pipecat/tree/8dff460307fda7d08531d4b9991cd0ad348d1a04/examples/websocket-server) by Pipecat
