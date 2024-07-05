#
# Copyright (c) 2024, Daily
# (Modified by Ayman Sah)
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import time
import os
import pvporcupine
from pvporcupine import Porcupine
import platform
import struct

from enum import Enum

from pipecat.frames.frames import ErrorFrame, Frame, AudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from loguru import logger


class CustomWakeCheckFilter(FrameProcessor):
    """
    This filter looks for wake phrases in the transcription frames and only passes through frames
    after a wake phrase has been detected. It also has a keepalive timeout to allow for a brief
    period of continued conversation after a wake phrase has been detected.
    """
    class WakeState(Enum):
        IDLE = 1
        AWAKE = 2
        
    class PicoHandle():
        """
        Used to initialize the Porcupine wake word detection engine.
        Requires an API key from PicoVoice and the appropriate keyword files.
        """
        def __init__(self,
                     picovoice_api_key = None,
                     keyword_path_windows: str = None,
                     keyword_path_linux: str = None,
                     keyword_path_mac: str = None
                     ) -> None:
            
            if picovoice_api_key is None:
                raise ValueError("PicoVoice API key is required.")
            
            if keyword_path_windows is None and keyword_path_linux is None and keyword_path_mac is None:
                raise ValueError("Atleast one keyword path is required.")
            
            self.current_platform = platform.system()
            if self.current_platform not in ["Windows", "Linux", "Darwin"]:
                raise OSError("Unsupported platform by PicoVoice.")
            self._api_key = picovoice_api_key
            self.path_windows = keyword_path_windows
            self.path_linux = keyword_path_linux
            self.path_mac = keyword_path_mac
            
        # Create the Porcupine handler based on the platform
        def create_handler(self) -> Porcupine:
            if self.current_platform == "Windows" and self.path_windows:
                directory, filename = os.path.split(self.path_windows)
                handler = pvporcupine.create(self._api_key, keyword_paths=[
                                            os.path.join(directory, filename)])

            if self.current_platform == "Linux" and self.path_linux:
                directory, filename = os.path.split(self.path_linux)
                handler = pvporcupine.create(self._api_key, keyword_paths=[
                                            os.path.join(directory, filename)])

            if self.current_platform == "Darwin" and self.path_mac:
                directory, filename = os.path.split(self.path_mac)
                handler = pvporcupine.create(self._api_key, keyword_paths=[
                                            os.path.join(directory, filename)])
            else:
                raise OSError("Atleast one keyword file must be provided or unsupported platform by PicoVoice.")
            return handler

    class ParticipantState:
        def __init__(self, participant_id: str):
            self.participant_id = participant_id
            self.state = CustomWakeCheckFilter.WakeState.IDLE
            self.wake_timer = 0.0
            self.accumulator = bytearray() # initialize as empty byte array to accumulate audio insteaad of text

    def __init__(self, keepalive_timeout: float = 3,
                 user_id: str = None,
                 keyword_path_windows: str = None,
                 keyword_path_linux: str = None,
                 keyword_path_mac: str = None):
        
        # Wake phrases are not used in this filter, instead we use the Porcupine wake word detection engine
        # so we pass an empty list to the super class
        super().__init__(wake_phrases=[""], keepalive_timeout=keepalive_timeout)
        
        self._participant_states = {}
        self._keepalive_timeout = keepalive_timeout
        self._wake_patterns = []
        
        # Initialize the Porcupine handler as a class attribute (atleast one keyword file is required)
        self.pico_handler = CustomWakeCheckFilter.PicoHandle(os.getenv("PICOVOICE_API_KEY"),
                                                                keyword_path_windows,
                                                                keyword_path_linux,
                                                                keyword_path_mac).create_handler()
                                                       
                                                       
        
        # variable to keep track of the state of the participant variable (if assigned or not)
        # so we do not run into issues with accessing the participant state
        self.p_assigned = False
        
        # User ID is required to keep track of the state of the participant
        # AudioRawFrame does not have a user_id attribute so we need to pass it in
        self.user_id = user_id

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        try:
            # If the frame is an AudioRawFrame, process it (instead of TranscriptionFrame as in the base class)
            if isinstance(frame, AudioRawFrame):
                p = self._participant_states.get(self.user_id)
                if not self.p_assigned:
                    if p is None:
                        p = CustomWakeCheckFilter.ParticipantState(self.user_id)
                        self._participant_states[self.user_id] = p
                    self.p_assigned = True

                # If we have been AWAKE within the last keepalive_timeout seconds, pass
                # the frame through
                if self.p_assigned and p is not None:
                    if p.state == CustomWakeCheckFilter.WakeState.AWAKE:
                        if time.time() - p.wake_timer < self._keepalive_timeout:
                            await self.push_frame(frame)
                            return
                        else:
                            p.state = CustomWakeCheckFilter.WakeState.IDLE
                            self.p_assigned = False
                            logger.debug("Wake phrase keepalive timeout has expired. Listening for wake word again.")
                            
                            # reseting wake timer here instead of in the above if block
                            # (previously reset in the above if block caused issues)
                            p.wake_timer = time.time()
                    
                    # accumulate audio outside loop to avoid losing audio / user input
                    p.accumulator += frame.audio    
                    
                    # if the previous FrameProcessor was interrupted (this attribute is added in the new CustomFrameProcessor class)
                    while self._prev._interrupted and p.state == CustomWakeCheckFilter.WakeState.IDLE:
                        # accumulate until we have enough audio to process (1024 samples is the max due to Porcupine's requirements)
                        if len(p.accumulator) >= 1024:
                            processing_audio = p.accumulator
                            
                            # Convert the audio to linear PCM and make into list (required by Porcupine to be 16-bit signed integers)
                            linear_audio = struct.unpack(str(len(processing_audio) // 2) + 'h', processing_audio)
                            linear_audio = list(linear_audio)
                            
                            # Process chunks of 512 samples (1024/2 bytes) at a time (Porcupine's requirements)
                            i = 0
                            while i < len(linear_audio):
                                chunk = linear_audio[i:i+512]
                                if len(chunk) == 512:
                                    self.match = self.pico_handler.process(chunk)
                                    if self.match >= 0:
                                        logger.debug("Porcupine wake word triggered")
                                        # Found the wake word. Discard from the accumulator up to the start of the match
                                        # and modify the frame in place.
                                        p.state = CustomWakeCheckFilter.WakeState.AWAKE
                                        p.wake_timer = time.time()
                                        p.accumulator = bytearray()
                                        await self.push_frame(frame)
                                        break  # Exit the loop if a match is found
                                i += 512
                            else:
                                pass
                        break
                    else:
                        pass
                else:
                    pass
            else:
                await self.push_frame(frame, direction)
        except Exception as e:
            error_msg = f"Error in wake word filter: {e}"
            logger.error(error_msg)
            await self.push_error(ErrorFrame(error_msg))
