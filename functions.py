from __init__ import AddableDict, logger

def process_questions():
    raise NotImplementedError("This function must be called asyncronously.")

async def process_questions_async(question: str | AddableDict | dict, userId: str = None):
            if isinstance(question, dict) or isinstance(question, AddableDict):
                quest = question.get("input", None)
                history = question.get("chat_history", [])
            
            if quest:
                # Add any steps to process the user input inlcuding history here
                data = f"Got Input: {quest}\nUser ID: {userId}"
                logger.debug(data)
                return data
            logger.debug("No user input found.")
            return "Got no user input."