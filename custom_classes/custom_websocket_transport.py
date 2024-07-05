#
# Copyright (c) 2024, Daily 
# (Modified by Ayman Sah)
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import asyncio

from pipecat.frames.frames import AudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams


from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    StartFrame,
    EndFrame,
    Frame,
    StartInterruptionFrame,
    StopInterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame)
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.network.websocket_server import WebsocketServerParams, WebsocketServerCallbacks, WebsocketServerOutputTransport

from pipecat.vad.vad_analyzer import VADAnalyzer, VADState

from loguru import logger

try:
    import websockets
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use websockets, you need to `pip install pipecat-ai[websocket]`.")
    raise Exception(f"Missing module: {e}")

from enum import Enum

from pipecat.frames.frames import ErrorFrame, Frame, MetricsFrame, StartFrame, UserStoppedSpeakingFrame
from pipecat.utils.utils import obj_count, obj_id


class CustomFrameProcessor(FrameProcessor):

    def __init__(
            self,
            name: str | None = None,
            loop: asyncio.AbstractEventLoop | None = None,
            **kwargs):
        
        super().__init__(name, loop, **kwargs)
        
        # Interrupted state
        self._interrupted = False


class CustomBaseInputTransport(BaseInputTransport):

    def __init__(self, params: TransportParams, **kwargs):
        super().__init__(params, **kwargs)
        
        self._interrupted = False

    #
    # Handle interruptions
    #

    async def _handle_interruptions(self, frame: Frame):
        if self.interruptions_allowed:
            # Make sure we notify about interruptions quickly out-of-band
            if isinstance(frame, UserStartedSpeakingFrame):
                logger.debug("User started speaking")
                
                self._interrupted = True # Set the interrupted state to True
                
                self._push_frame_task.cancel()
                await self._push_frame_task
                await self.push_frame(StartInterruptionFrame())
                self._create_push_task()
            elif isinstance(frame, UserStoppedSpeakingFrame):
                logger.debug("User stopped speaking")
                
                self._interrupted = False # Set the interrupted state to False
                
                await self.push_frame(StopInterruptionFrame())
        await self._internal_push_frame(frame)

    #
    # Audio input
    #

    async def _vad_analyze(self, audio_frames: bytes) -> VADState:
        state = VADState.QUIET
        vad_analyzer = self.vad_analyzer()
        if vad_analyzer:
            state = await self.get_event_loop().run_in_executor(
                self._executor, vad_analyzer.analyze_audio, audio_frames)
        return state

    async def _handle_vad(self, audio_frames: bytes, vad_state: VADState):
        new_vad_state = await self._vad_analyze(audio_frames)
        if new_vad_state != vad_state and new_vad_state != VADState.STARTING and new_vad_state != VADState.STOPPING:
            frame = None
            if new_vad_state == VADState.SPEAKING:
                frame = UserStartedSpeakingFrame()
            elif new_vad_state == VADState.QUIET:
                frame = UserStoppedSpeakingFrame()

            if frame:
                await self._handle_interruptions(frame)

            vad_state = new_vad_state
        return vad_state




class CustomWebsocketServerInputTransport(CustomBaseInputTransport):

    def __init__(
            self,
            host: str,
            port: int,
            params: WebsocketServerParams,
            callbacks: WebsocketServerCallbacks,
            **kwargs):
        super().__init__(params, **kwargs)

        self._host = host
        self._port = port
        self._params = params
        self._callbacks = callbacks

        self._websocket: websockets.WebSocketServerProtocol | None = None

        self._stop_server_event = asyncio.Event()

    async def start(self, frame: StartFrame):
        self._server_task = self.get_event_loop().create_task(self._server_task_handler())
        await super().start(frame)

    async def stop(self):
        self._stop_server_event.set()
        await self._server_task
        await super().stop()

    async def _server_task_handler(self):
        logger.info(f"Starting websocket server on {self._host}:{self._port}")
        async with websockets.serve(self._client_handler, self._host, self._port) as server:
            await self._stop_server_event.wait()

    async def _client_handler(self, websocket: websockets.WebSocketServerProtocol, path):
        logger.info(f"New client connection from {websocket.remote_address}")
        if self._websocket:
            await self._websocket.close()
            logger.warning("Only one client connected, using new connection")

        self._websocket = websocket

        # Notify
        await self._callbacks.on_client_connected(websocket)

        # Handle incoming messages
        async for message in websocket:
            frame = self._params.serializer.deserialize(message)

            if not frame:
                continue

            if isinstance(frame, AudioRawFrame):
                await self.push_audio_frame(frame)
            else:
                await self._internal_push_frame(frame)

        # Notify disconnection
        await self._callbacks.on_client_disconnected(websocket)

        await self._websocket.close()
        self._websocket = None

        logger.info(f"Client {websocket.remote_address} disconnected")


class CustomWebsocketServerTransport(BaseTransport):

    def __init__(
            self,
            host: str = "localhost",
            port: int = 8765,
            params: WebsocketServerParams = WebsocketServerParams(),
            input_name: str | None = None,
            output_name: str | None = None,
            loop: asyncio.AbstractEventLoop | None = None):
        super().__init__(input_name=input_name, output_name=output_name, loop=loop)
        self._host = host
        self._port = port
        self._params = params

        self._callbacks = WebsocketServerCallbacks(
            on_client_connected=self._on_client_connected,
            on_client_disconnected=self._on_client_disconnected
        )
        self._input: CustomWebsocketServerInputTransport | None = None
        self._output: WebsocketServerOutputTransport | None = None
        self._websocket: websockets.WebSocketServerProtocol | None = None

        # Register supported handlers. The user will only be able to register
        # these handlers.
        self._register_event_handler("on_client_connected")
        self._register_event_handler("on_client_disconnected")

    def input(self) -> FrameProcessor:
        if not self._input:
            self._input = CustomWebsocketServerInputTransport(
                self._host, self._port, self._params, self._callbacks, name=self._input_name)
        return self._input

    def output(self) -> FrameProcessor:
        if not self._output:
            self._output = WebsocketServerOutputTransport(self._params, name=self._output_name)
        return self._output

    async def _on_client_connected(self, websocket):
        if self._output:
            await self._output.set_client_connection(websocket)
            await self._call_event_handler("on_client_connected", websocket)
        else:
            logger.error("A WebsocketServerTransport output is missing in the pipeline")

    async def _on_client_disconnected(self, websocket):
        if self._output:
            await self._output.set_client_connection(None)
            await self._call_event_handler("on_client_disconnected", websocket)
        else:
            logger.error("A WebsocketServerTransport output is missing in the pipeline")
