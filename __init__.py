# Used for imports

import asyncio
import aiohttp
import os
import sys

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator, LLMUserResponseAggregator)
from pipecat.processors.frameworks.langchain import LangchainProcessor
from pipecat.services.elevenlabs import ElevenLabsTTSService
from pipecat.services.deepgram import DeepgramSTTService 
from pipecat.vad.silero import SileroVADAnalyzer
from langchain_core.runnables.base import RunnableLambda
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from openai import AsyncOpenAI
from langchain_core.runnables.utils import AddableDict
import random


from custom_classes.custom_wake_word import CustomWakeCheckFilter
from custom_classes.custom_websocket_transport import WebsocketServerParams, CustomWebsocketServerTransport


from loguru import logger

from dotenv import load_dotenv
load_dotenv(override=True)
