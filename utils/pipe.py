
from __init__ import *
from utils.functions import process_questions_async, process_questions


logger.remove(0)
logger.add(sys.stderr, level="DEBUG")
message_store = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in message_store:
        message_store[session_id] = ChatMessageHistory()
    return message_store[session_id]


# async def call_pipecat(room_url: str, token):
async def call_pipecat(user_id: str):
    async with aiohttp.ClientSession() as session:
        transport = CustomWebsocketServerTransport(
            params=WebsocketServerParams(
                audio_out_enabled=True,
                add_wav_header=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                vad_audio_passthrough=True
            )
        )
        

        tts = ElevenLabsTTSService(
            aiohttp_session=session,
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        )
                
        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))


        chain = RunnableLambda(func=lambda x: process_questions(x),
                               afunc=lambda x: process_questions_async(x, user_id))
        
        history_chain = RunnableWithMessageHistory(
            chain,
            get_session_history,
            history_messages_key="chat_history",
            input_messages_key="input",)
        lc = LangchainProcessor(history_chain)

        tma_in = LLMUserResponseAggregator()
        tma_out = LLMAssistantResponseAggregator()
        pico_wake_word = CustomWakeCheckFilter(20, user_id)


        pipeline = Pipeline(
            [
                transport.input(),      # Transport user input
                pico_wake_word,         # Porcupine wake word
                stt,                    # STT
                tma_in,                 # User responses
                lc,                     # Langchain
                tts,                    # TTS
                transport.output(),     # Transport bot output
                tma_out,                # Assistant spoken responses
            ]
        )

        task = PipelineTask(pipeline, PipelineParams(allow_interruptions=True))

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            lc.set_participant_id(user_id)
            await tts.say(random.choice(["Hey.", "Hello."]))

        runner = PipelineRunner()

        await runner.run(task)

