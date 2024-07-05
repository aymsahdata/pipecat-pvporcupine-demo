# Pipecat + Picovoice Porcupine

### Get Started

- Fill out `.env` with the required environment variables for OpenAI (if needed), Picovoice, Elevenlabs, and Deepgram
- Install required libraries `pip install -r requirements.txt`
- Get the needed .ppn files from Picovoice Developer Console and place them in `keyword_files/` directory or any other
- Direct the wake word filter to the keyword files depending on your OS:
    `utils/pipe.py`:
      Line 52 - `pico_wake_word = CustomWakeCheckFilter(20, user_id, keyword_path_mac="keyword_files/hey_pipe_mac.ppn")`

- Run `main.py` and navigate to `http://localhost:8000` to test
