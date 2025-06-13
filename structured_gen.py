import requests
import json
import re
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Dict

import os
import dotenv

dotenv.load_dotenv()

# Use Ollama instead of Modal/vLLM
CLIENT = OpenAI(
    base_url="http://localhost:11434/v1/",
    api_key="ollama",  # Ollama doesn't require a real API key
)

print("Using base URL:", CLIENT.base_url)

# Set a specific chat model instead of auto-detecting
DEFAULT_MODEL = "llama3.2"  # Use a known chat model

try:
    MODELS = CLIENT.models.list()
    available_models = [model.id for model in MODELS.data]
    print("Available models:", available_models)
    
    # Prefer specific chat models
    chat_models = ["llama3.2", "llama3.1", "llama3", "qwen2.5", "phi3", "mistral"]
    for model in chat_models:
        if model in available_models:
            DEFAULT_MODEL = model
            break
    
    print("Using chat model:", DEFAULT_MODEL)
except Exception as e:
    print(f"Could not fetch models from Ollama: {e}")
    print("Using fallback model:", DEFAULT_MODEL)

MAX_TOKENS = 4000


def repair_json(text: str) -> str:
    """Attempt to repair common JSON issues"""
    import json
    
    # First, fix basic syntax issues
    # Fix unquoted keys (simpler approach)
    text = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', text)
    
    # Fix trailing commas
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    
    # Fix corrupted quotes in text content (person"s -> person's)
    text = re.sub(r'(\w)"(\w)', r"\1'\2", text)
    
    # Try to parse and fix the structure
    try:
        data = json.loads(text)
        
        # Fix questions format: string -> object
        if 'questions' in data and isinstance(data['questions'], list):
            for i, item in enumerate(data['questions']):
                if isinstance(item, str):
                    data['questions'][i] = {"type": "Question", "text": item}
        
        # Fix concepts format: string -> object or add missing fields
        if 'concepts' in data and isinstance(data['concepts'], list):
            for i, item in enumerate(data['concepts']):
                if isinstance(item, str):
                    data['concepts'][i] = {
                        "type": "Concept", 
                        "text": item.lower(),
                        "relationship_type": "CONNECTS_TO"
                    }
                elif isinstance(item, dict):
                    # Fix the type field - should always be "Concept"
                    item['type'] = 'Concept'
                    
                    # Fix text field - ensure lowercase and pattern compliance
                    if 'text' in item:
                        # Clean up the text: only lowercase letters and spaces
                        cleaned_text = re.sub(r'[^a-z\s]', '', item['text'].lower())
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        item['text'] = cleaned_text or 'concept'
                    
                    # Fix relationship_type
                    if 'relationship_type' not in item or item.get('relationship_type') not in ['IS_A', 'AFFECTS', 'CONNECTS_TO']:
                        item['relationship_type'] = 'CONNECTS_TO'
                    
                    # Remove extra fields that aren't part of the schema
                    allowed_fields = {'type', 'text', 'relationship_type'}
                    keys_to_remove = [k for k in item.keys() if k not in allowed_fields]
                    for k in keys_to_remove:
                        del item[k]
        
        # Fix answer format: string -> object
        if 'answer' in data and isinstance(data['answer'], list):
            for i, item in enumerate(data['answer']):
                if isinstance(item, str):
                    data['answer'][i] = {"type": "Answer", "text": item}
        
        # Ensure required fields exist based on common patterns
        if 'questions' in data and 'concepts' not in data:
            data['concepts'] = []
        if 'concepts' in data and 'questions' not in data:
            data['questions'] = []
        if 'answer' in data and isinstance(data['answer'], list) and len(data['answer']) == 0:
            data['answer'] = [{"type": "Answer", "text": "No specific answer provided."}]
        
        # Special case: if we have questions/concepts but expected answer format
        # This happens when the AI generates the wrong format for Question nodes
        if 'questions' in data and 'concepts' in data and 'answer' not in data:
            # Check if this might be a FromQuestion case by looking for context clues
            # For now, we'll let it pass and rely on the caller to determine the right format
            pass
        
        return json.dumps(data, ensure_ascii=False)
        
    except json.JSONDecodeError as e:
        # If JSON is still invalid, try to extract a valid subset
        print(f"JSON repair failed: {e}")
        # Try to find the valid part before the error
        try:
            # Find where the JSON becomes invalid and truncate
            error_pos = getattr(e, 'pos', len(text))
            truncated = text[:error_pos]
            
            # Try to close any open braces/brackets
            open_braces = truncated.count('{') - truncated.count('}')
            open_brackets = truncated.count('[') - truncated.count(']')
            
            for _ in range(open_brackets):
                truncated += ']'
            for _ in range(open_braces):
                truncated += '}'
            
            # Try to parse the truncated version
            data = json.loads(truncated)
            
            # Add missing required fields
            if 'questions' in data and 'concepts' not in data:
                data['concepts'] = []
            if 'concepts' in data and 'questions' not in data:
                data['questions'] = []
            
            return json.dumps(data, ensure_ascii=False)
            
        except:
            # Last resort: create a minimal valid structure
            return '{"questions": [], "concepts": []}'
    
    return text

def extract_json_from_response(text: str) -> str:
    """Extract JSON from a response that might contain extra text"""
    import json
    
    # Try to find JSON in code blocks first
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        candidate = json_match.group(1).strip()
        try:
            # Validate the JSON
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            # Try to repair and validate
            repaired = repair_json(candidate)
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                pass
    
    # Try to find JSON object in the text with better matching
    # Look for balanced braces
    brace_count = 0
    start_pos = -1
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                start_pos = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_pos != -1:
                candidate = text[start_pos:i+1]
                try:
                    # Validate the JSON
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    # Try to repair and validate
                    repaired = repair_json(candidate)
                    try:
                        json.loads(repaired)
                        return repaired
                    except json.JSONDecodeError:
                        continue
    
    # If no valid JSON found, try to clean up the text
    # Remove common issues
    cleaned = text.strip()
    
    # Remove trailing text after potential JSON
    if '{' in cleaned and '}' in cleaned:
        start = cleaned.find('{')
        # Find the last } that could close the JSON
        end = cleaned.rfind('}') + 1
        candidate = cleaned[start:end]
        
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            # Try to repair and validate
            repaired = repair_json(candidate)
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                pass
    
    # Last resort: try to repair the entire text
    repaired = repair_json(text.strip())
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        pass
    
    # Final fallback: return original text and let the caller handle the error
    return text.strip()


def messages(user: str, system: str = "You are a helpful assistant."):
    ms = [{"role": "user", "content": user}]
    if system:
        ms.insert(0, {"role": "system", "content": system})
    return ms


def generate(
    messages: List[Dict[str, str]],
    response_format: BaseModel,
) -> BaseModel:
    # Add JSON schema instruction to the system message
    schema_instruction = f"\nPlease respond with valid JSON that matches this schema: {response_format.model_json_schema()}"
    
    # Create a copy to avoid modifying the original
    messages_copy = messages.copy()
    
    # Modify the system message to include JSON instruction
    if messages_copy and messages_copy[0]["role"] == "system":
        messages_copy[0] = messages_copy[0].copy()
        messages_copy[0]["content"] += schema_instruction
    else:
        messages_copy.insert(0, {"role": "system", "content": "You are a helpful assistant." + schema_instruction})
    
    response = CLIENT.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages_copy,
        max_tokens=MAX_TOKENS,
    )
    return response


def generate_by_schema(
    messages: List[Dict[str, str]],
    schema: str,
) -> BaseModel:
    # Parse schema to determine the correct format
    import json
    try:
        schema_obj = json.loads(schema)
        properties = schema_obj.get('properties', {})
        
        # Determine format based on properties
        if 'answer' in properties:
            # FromQuestion format
            example_json = """{
  "answer": [
    {
      "type": "Answer",
      "text": "Detailed answer to the question"
    }
  ]
}"""
            rules = """Rules:
- answer: Array of objects with "type": "Answer" and "text": "answer text"
- Provide thoughtful, detailed answers to the question"""

        elif 'questions' in properties and 'concepts' in properties:
            # FromConcept format
            example_json = """{
  "questions": [
    {
      "type": "Question",
      "text": "What specific aspect do you want to explore?"
    }
  ],
  "concepts": [
    {
      "type": "Concept", 
      "text": "lowercase concept name",
      "relationship_type": "CONNECTS_TO"
    }
  ]
}"""
            rules = """Rules:
- questions: Array of objects with "type": "Question" and "text": "question text"
- concepts: Array of objects with "type": "Concept", "text": "lowercase text only", "relationship_type": "IS_A" or "AFFECTS" or "CONNECTS_TO"
- concept text must be lowercase letters and spaces only
- relationship_type must be exactly one of: "IS_A", "AFFECTS", "CONNECTS_TO" """

        else:
            # FromAnswer format (concepts and questions)
            example_json = """{
  "concepts": [
    {
      "type": "Concept",
      "text": "lowercase concept name"
    }
  ],
  "questions": [
    {
      "type": "Question",
      "text": "What new question emerges?"
    }
  ]
}"""
            rules = """Rules:
- concepts: Array of objects with "type": "Concept" and "text": "lowercase text only"
- questions: Array of objects with "type": "Question" and "text": "question text"
- concept text must be lowercase letters and spaces only"""

    except:
        # Fallback
        example_json = '{"questions": [], "concepts": []}'
        rules = "Return valid JSON with the requested fields."
    
    # Add JSON schema instruction to the system message
    schema_instruction = f"""

IMPORTANT: You must respond with ONLY valid JSON data in this exact format:

{example_json}

{rules}

Return only the JSON data object with your actual content, nothing else."""
    
    # Create a copy to avoid modifying the original
    messages_copy = messages.copy()
    
    # Modify the system message to include JSON instruction
    if messages_copy and messages_copy[0]["role"] == "system":
        messages_copy[0] = messages_copy[0].copy()
        messages_copy[0]["content"] += schema_instruction
    else:
        messages_copy.insert(0, {"role": "system", "content": "You are a helpful assistant." + schema_instruction})
    
    response = CLIENT.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages_copy,
        max_tokens=MAX_TOKENS,
    )
    return response


def choose(
    messages: List[Dict[str, str]],
    choices: List[str],
) -> str:
    # Add choice instruction to the system message
    choice_instruction = f"\nPlease respond with exactly one of these choices: {', '.join(choices)}"
    
    # Create a copy to avoid modifying the original
    messages_copy = messages.copy()
    
    # Modify the system message to include choice instruction
    if messages_copy and messages_copy[0]["role"] == "system":
        messages_copy[0] = messages_copy[0].copy()
        messages_copy[0]["content"] += choice_instruction
    else:
        messages_copy.insert(0, {"role": "system", "content": "You are a helpful assistant." + choice_instruction})
    
    completion = CLIENT.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages_copy,
        max_tokens=MAX_TOKENS,
    )
    return completion.choices[0].message.content.strip()


def regex(
    messages: List[Dict[str, str]],
    regex: str,
) -> str:
    # Add regex instruction to the system message
    regex_instruction = f"\nPlease respond with text that matches this regex pattern: {regex}"
    
    # Modify the system message to include regex instruction
    if messages and messages[0]["role"] == "system":
        messages[0]["content"] += regex_instruction
    else:
        messages.insert(0, {"role": "system", "content": "You are a helpful assistant." + regex_instruction})
    
    completion = CLIENT.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
    )
    return completion.choices[0].message.content.strip()


def embed(content: str) -> List[float]:
    """Generate embeddings using Ollama's embedding API"""
    try:
        response = requests.post(
            "http://localhost:11434/api/embeddings",
            json={
                "model": "nomic-embed-text",  # Default embedding model for Ollama
                "prompt": content
            }
        )
        response.raise_for_status()
        return response.json()["embedding"]
    except Exception as e:
        print(f"Error generating embedding: {e}")
        # Return a zero vector as fallback (768 dimensions for nomic-embed-text)
        return [0.0] * 768
