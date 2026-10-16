"""
Prompt management for WorkbenchIQ.
Handles loading and saving persona-specific prompts.
"""
import json
import os
from typing import Dict, Any, Optional, Union
from .personas import PersonaType, get_default_prompts


def _get_prompts_file_path(storage_root: str) -> str:
    """Get the path to the prompts file within a storage root."""
    return os.path.join(storage_root, "prompts.json")


def load_prompts(storage_root: str, persona: Union[PersonaType, str] = PersonaType.UNDERWRITING) -> Dict[str, Any]:
    """
    Load prompts for a specific persona.
    
    First tries to load from the prompts file. If the persona-specific
    prompts don't exist, falls back to default prompts from personas module.
    
    Args:
        storage_root: Path to the data storage directory (e.g., "data/")
        persona: The persona type to load prompts for (PersonaType or string)
        
    Returns:
        Dictionary containing the prompts for the persona
    """
    # Convert string to PersonaType if needed
    if isinstance(persona, str):
        try:
            persona = PersonaType(persona)
        except ValueError:
            persona = PersonaType.UNDERWRITING
    
    prompts_file = _get_prompts_file_path(storage_root)
    
    try:
        if os.path.exists(prompts_file):
            with open(prompts_file, 'r') as f:
                all_prompts = json.load(f)
                
            # Check if prompts are organized by persona
            if persona.value in all_prompts:
                return all_prompts[persona.value]
            
            # Legacy format: prompts not organized by persona
            # Return as-is for backward compatibility (assumes underwriting)
            if persona == PersonaType.UNDERWRITING:
                # Check for legacy format indicators
                if "application_summary" in all_prompts or "medical_summary" in all_prompts:
                    return all_prompts
                
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load prompts from {prompts_file}: {e}")
    
    # Fall back to default prompts for the persona
    return get_default_prompts(persona)


def save_prompts(storage_root: str, prompts: Dict[str, Any], persona: Union[PersonaType, str] = PersonaType.UNDERWRITING) -> bool:
    """
    Save prompts for a specific persona.
    
    For backward compatibility, if persona is UNDERWRITING and the file
    is in legacy format (no persona keys), it saves in legacy format.
    Otherwise, prompts are organized by persona in the JSON file.
    
    Args:
        storage_root: Path to the data storage directory (e.g., "data/")
        prompts: The prompts dictionary to save
        persona: The persona type to save prompts for
        
    Returns:
        True if save was successful, False otherwise
    """
    # Convert string to PersonaType if needed
    if isinstance(persona, str):
        try:
            persona = PersonaType(persona)
        except ValueError:
            persona = PersonaType.UNDERWRITING
    
    prompts_file = _get_prompts_file_path(storage_root)
    
    try:
        # Load existing prompts to check format
        existing_prompts = {}
        is_legacy_format = False
        
        if os.path.exists(prompts_file):
            try:
                with open(prompts_file, 'r') as f:
                    existing_prompts = json.load(f)
                # Check if legacy format (has section keys like "application_summary")
                is_legacy_format = ("application_summary" in existing_prompts or 
                                    "medical_summary" in existing_prompts)
            except (json.JSONDecodeError, IOError):
                pass
        
        # For backward compatibility: if underwriting and legacy format, save directly
        if persona == PersonaType.UNDERWRITING and is_legacy_format:
            with open(prompts_file, 'w') as f:
                json.dump(prompts, f, indent=2)
            return True
        
        # Otherwise, organize by persona
        if is_legacy_format:
            # Migrate: existing becomes underwriting
            all_prompts = {
                PersonaType.UNDERWRITING.value: existing_prompts
            }
        else:
            all_prompts = existing_prompts
        
        # Update prompts for the specified persona
        all_prompts[persona.value] = prompts
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(prompts_file), exist_ok=True)
        
        with open(prompts_file, 'w') as f:
            json.dump(all_prompts, f, indent=2)
            
        return True
        
    except (IOError, OSError) as e:
        print(f"Error saving prompts to {prompts_file}: {e}")
        return False


def get_all_persona_prompts(storage_root: str) -> Dict[str, Dict[str, Any]]:
    """
    Load prompts for all personas.
    
    Args:
        storage_root: Path to the data storage directory
        
    Returns:
        Dictionary mapping persona IDs to their prompts
    """
    result = {}
    for persona in PersonaType:
        result[persona.value] = load_prompts(storage_root, persona)
    return result
