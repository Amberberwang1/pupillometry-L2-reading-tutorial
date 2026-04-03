"""
Condition Mapping Utility
Supplementary materials for: "Pupillometry for L2 reading research"

Maps Block B file identifiers to experimental conditions:
  ss = Simplified-primed (simplified prime → simplified target)
  ns = Non-simplified-primed (non-simplified prime → simplified target)

Imported by other scripts; not run independently as part of the pipeline.
"""

def get_block_b_condition(participant_id):
    """
    Map Block B participant/session identifier to condition
    
    Parameters:
    -----------
    participant_id : str
        Participant identifier (e.g., '01', '02_b', '03_a', '04_ns')
    
    Returns:
    --------
    str
        Condition: 'ss' (Simplified Structure) or 'ns' (No Simplification)
    """
    # Mapping based on clarification: a=ss, b=ns
    
    # Participant 01 - NS condition based on data
    if participant_id == '01':
        return 'ns'  # No Simplification
    
    # Participant 02
    if participant_id == '02':
        return 'ss'  # Simplified Structure
    if participant_id == '02_b':
        return 'ns'  # No Simplification
    
    # Participants 03-06 with 'a' suffix = ss (Simplified Structure)
    if participant_id in ['03_a', '04_ss', '05_SS', '06_SS']:
        return 'ss'
    
    # Participants 03-06 with 'b' suffix = ns (No Simplification)
    if participant_id in ['03_b', '04_ns', '05_ns', '06_NS']:
        return 'ns'
    
    return 'unknown'

def get_all_block_b_mappings():
    """
    Get complete mapping of all Block B files to conditions
    
    Returns:
    --------
    dict
        Dictionary mapping participant IDs to conditions
    """
    mappings = {
        # Participant 01
        '01': 'ns',      # No Simplification
        
        # Participant 02
        '02': 'ss',      # Simplified Structure
        '02_b': 'ns',    # No Simplification
        
        # Participant 03
        '03_a': 'ss',    # Simplified Structure
        '03_b': 'ns',    # No Simplification
        
        # Participant 04
        '04_ss': 'ss',   # Simplified Structure
        '04_ns': 'ns',   # No Simplification
        
        # Participant 05
        '05_SS': 'ss',   # Simplified Structure
        '05_ns': 'ns',   # No Simplification
        
        # Participant 06
        '06_SS': 'ss',   # Simplified Structure
        '06_NS': 'ns',   # No Simplification
    }
    
    return mappings

def print_condition_summary():
    """
    Print a summary of condition mappings
    """
    print("=" * 70)
    print("BLOCK B CONDITION MAPPING")
    print("=" * 70)
    print("\nConditions:")
    print("  ss = Simplified Structure (labeled as 'a' in some files)")
    print("  ns = No Simplification (labeled as 'b' in some files)")
    print("\nMapping:")
    print("-" * 70)
    
    mappings = get_all_block_b_mappings()
    
    # Group by participant
    participants = {}
    for file_id, condition in mappings.items():
        # Extract participant number
        p_num = file_id.split('_')[0]
        if p_num not in participants:
            participants[p_num] = {}
        participants[p_num][file_id] = condition
    
    for p_num in sorted(participants.keys()):
        print(f"\nParticipant {p_num}:")
        for file_id, condition in sorted(participants[p_num].items()):
            print(f"  {file_id:12s} → {condition} ({get_condition_name(condition)})")
    
    print("\n" + "=" * 70)

def get_condition_name(condition_code):
    """
    Get full condition name from code
    """
    names = {
        'ss': 'Simplified Structure',
        'ns': 'No Simplification'
    }
    return names.get(condition_code, 'Unknown')

if __name__ == "__main__":
    print_condition_summary()

