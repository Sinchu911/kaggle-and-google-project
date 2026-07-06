import logging
import os
import re
import anthropic
import json
from google import genai
from google.adk.agents.llm_agent import Agent
from google.adk.runners import InMemoryRunner
from google.genai import types
from app.tools import ReceiptOutput
from app.config import settings

# Setup logging
logger = logging.getLogger("ReceiptParser")

# Configure model name (Gemini 3.5 Flash)
# Using "gemini-2.5-flash" (or similar) as the actual model string
MODEL_NAME = "gemini-2.5-flash"

# Define Agent 1: Receipt Parser
receipt_parser_agent = Agent(
    name="receipt_parser",
    model=MODEL_NAME,
    instruction=(
        "You are an automated receipt parsing agent. Your job is to extract structured details from "
        "raw, unstructured expense notes or receipt texts. You must populate the fields in the "
        "ReceiptOutput schema:\n"
        "1. amount: The cost or charge amount as a float.\n"
        "2. currency: The 3-letter currency code (e.g., USD, EUR, JPY, AUD).\n"
        "3. country: The country name where the purchase occurred (e.g., Germany, Italy, Japan, United States).\n"
        "4. has_pii: Set to True if the text contains sensitive credentials, full email addresses, passwords, or credit card numbers.\n\n"
        "You MUST invoke the `set_model_response` tool with the extracted data structured "
        "exactly as specified in the schema."
    ),
    output_schema=ReceiptOutput
)

def parse_receipt(text: str) -> ReceiptOutput | None:
    """
    Accepts raw unstructured receipt text, processes it using the receipt parser agent,
    and returns a structured ReceiptOutput Pydantic object.
    """
    logger.info(f"Parsing receipt text input: {repr(text)}")

    def deterministic_local_receipt_fallback(raw_text: str) -> ReceiptOutput:
        lower_text = raw_text.lower()
        currency = "JPY" if "jpy" in lower_text or "¥" in raw_text else "USD"
        country = "Japan" if "japan" in lower_text else "Unknown"

        # Extract the largest numeric amount from the raw text.
        numeric_matches = re.findall(r"\d{1,3}(?:[,\s-]\d{3})*(?:\.\d+)?|\d+\.\d+", raw_text)
        amount_values = []
        for num in numeric_matches:
            cleaned = num.replace(",", "").replace(" ", "")
            try:
                amount_values.append(float(cleaned))
            except ValueError:
                continue

        amount = max(amount_values) if amount_values else 0.0
        has_pii = any(token in lower_text for token in ["email", "@", "password", "credit card", "card number", "ssn", "credentials"])

        logger.warning(
            "Using deterministic local receipt fallback. "
            f"Extracted amount={amount}, currency={currency}, country={country}, has_pii={has_pii}"
        )

        return ReceiptOutput(
            amount=amount,
            currency=currency,
            country=country,
            has_pii=has_pii
        )

    # Instantiate in-memory runner to execute the agentic workflow
    runner = InMemoryRunner(agent=receipt_parser_agent)
    runner.auto_create_session = True
    
    try:
        # Wrap input message in the Google GenAI types Content schema
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=text)]
        )
        
        # Run agent to completion
        events = runner.run(
            user_id="user_parser",
            session_id="session_parser",
            new_message=user_message
        )
        
        final_output = None
        raw_text = ""
        
        # Iterate over events to collect any direct outputs or text pieces
        for event in events:
            if event.output:
                final_output = event.output
            if event.content and hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if part.text:
                        raw_text += part.text
            elif hasattr(event, "text") and event.text:
                raw_text += event.text
        
        response = final_output
        extracted_val = None
        
        if response:
            logger.info(f"Live Gemini response type detected: {type(response)}")
            if isinstance(response, ReceiptOutput):
                extracted_val = response
            elif isinstance(response, dict):
                extracted_val = response
            else:
                # Check direct common attributes dynamically
                for attr in ['structured_output', 'parsed', 'output', 'content', 'text']:
                    if hasattr(response, attr):
                        val = getattr(response, attr)
                        if val:
                            logger.info(f"Successfully extracted data from attribute: '{attr}'")
                            if isinstance(val, (ReceiptOutput, dict)):
                                extracted_val = val
                                break
                            elif isinstance(val, str):
                                raw_text += val
                
                # Deep extraction fallback for raw Google GenAI structure
                if not extracted_val and hasattr(response, 'candidates') and response.candidates:
                    try:
                        cand_text = response.candidates[0].content.parts[0].text
                        if cand_text:
                            raw_text += cand_text
                    except Exception:
                        pass
        
        # If we have raw text accumulated and no structured object yet, parse it
        if not extracted_val and raw_text:
            cleaned_text = raw_text.strip()
            if cleaned_text.startswith("```"):
                lines = cleaned_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_text = "\n".join(lines).strip()
            try:
                data = json.loads(cleaned_text)
                if isinstance(data, dict):
                    extracted_val = data
            except Exception:
                pass
        
        if extracted_val is not None:
            if isinstance(extracted_val, ReceiptOutput):
                return extracted_val
            elif isinstance(extracted_val, dict):
                # Ensure has_pii is present in data
                if "has_pii" not in extracted_val:
                    lower_text = text.lower()
                    has_pii = any(k in lower_text for k in ["email", "@", "password", "credit card", "card:", "card #", "card number", "ssn", "credentials"])
                    extracted_val["has_pii"] = has_pii
                return ReceiptOutput(**extracted_val)
        
        # If we couldn't get a structured value, raise ValueError to trigger fallback
        raise ValueError("Failed to extract valid structured receipt data from Gemini response.")
        
    except Exception as e:
        logger.exception("Gemini parsing original error details:")
        logger.warning("⚠️ Gemini primary path failed for Agent 1 Parser! Falling back to Anthropic Claude...")
        try:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("ANTHROPIC_API_KEY is not set. Fallback failed.")
                return None
            
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                tools=[
                    {
                        "name": "parse_receipt",
                        "description": "Extract details from receipt",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "amount": {
                                    "type": "number",
                                    "description": "The cost or charge amount as a float."
                                },
                                "currency": {
                                    "type": "string",
                                    "description": "The 3-letter currency code (e.g., USD, EUR, JPY)."
                                },
                                "country": {
                                    "type": "string",
                                    "description": "The country name where the purchase occurred."
                                },
                                "has_pii": {
                                    "type": "boolean",
                                    "description": "Set to True if the text contains sensitive credentials, full email addresses, passwords, or credit card numbers."
                                }
                            },
                            "required": ["amount", "currency", "country", "has_pii"]
                        }
                    }
                ],
                tool_choice={"type": "tool", "name": "parse_receipt"},
                messages=[
                    {"role": "user", "content": text}
                ]
            )
            
            tool_use = None
            for block in response.content:
                if block.type == "tool_use" and block.name == "parse_receipt":
                    tool_use = block
                    break
            
            if tool_use:
                return ReceiptOutput(**tool_use.input)
            
            logger.error("Claude did not return a tool call. Falling back to deterministic local parser.")
            return deterministic_local_receipt_fallback(text)
        except Exception as claude_err:
            logger.error(f"Fallback to Anthropic Claude failed: {claude_err}", exc_info=True)
            return deterministic_local_receipt_fallback(text)
