import uuid

def generate_uuid_from_title(title):
    """Generate a deterministic UUID from a title using UUID5."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, title))

def normalize_scores(scores_dict, min_value=8):
    """
    Normalize scores to ensure they sum to 100 and each value is at least min_value.
    
    Args:
        scores_dict (dict): Dictionary containing scores
        min_value (int): Minimum allowed value, defaults to 8
        
    Returns:
        dict: Normalized scores dictionary
    """
    if not scores_dict:
        return {}
    
    total = sum(scores_dict.values())
    
    if total == 0:
        count = len(scores_dict)
        if count == 0:
            return {}
        
        even_value = (100 - min_value * count) / count + min_value
        return {k: round(even_value, 2) for k in scores_dict}
    
    reserved_points = min_value * len(scores_dict)
    remaining_points = 100 - reserved_points
    
    if remaining_points < 0:
        avg_value = 100 / len(scores_dict)
        return {k: round(avg_value, 2) for k in scores_dict}
    
    scaled_dict = {}
    for k, v in scores_dict.items():
        scaled_dict[k] = min_value
        if total > 0:
            scaled_dict[k] += (v / total) * remaining_points
    
    result = {k: round(v, 2) for k, v in scaled_dict.items()}
    
    current_sum = sum(result.values())
    if abs(current_sum - 100) > 0.01:
        max_key = max(result, key=result.get)
        result[max_key] = round(result[max_key] + (100 - current_sum), 2)
    
    for k in result:
        if result[k] < min_value:
            result[k] = min_value
    
    final_sum = sum(result.values())
    if abs(final_sum - 100) > 0.01:
        max_key = max(result, key=result.get)
        result[max_key] = round(result[max_key] + (100 - final_sum), 2)
    
    return result

def process_emotion_stance_data(data):
    """
    Process emotion and stance data, ensuring scores are properly normalized.
    
    Args:
        data (dict): Data item to process
    
    Returns:
        dict: Processed data item
    """
    if "emotion" in data and "schema" in data["emotion"]:
        emotion_schema = data["emotion"]["schema"]
        if all(v < 1 for v in emotion_schema.values()):
            emotion_schema = {k: v * 100 for k, v in emotion_schema.items()}
        data["emotion"]["schema"] = normalize_scores(emotion_schema)
    
    if "stance" in data and "schema" in data["stance"]:
        stance_schema = data["stance"]["schema"]
        if all(v < 1 for v in stance_schema.values()):
            stance_schema = {k: v * 100 for k, v in stance_schema.items()}
        data["stance"]["schema"] = normalize_scores(stance_schema)
    
    return data 