"""Native 0x414850 background selection (include_object=0 path only)."""

def select_background(definitions, class_id, parameter):
    best = None
    best_score = -1
    parameter &= 65535
    for definition in definitions:
        program = definition['byte_raw']
        score = -1 if 0 < program < 255 else 0
        if definition['leading_bytes_raw'][1] == class_id:
            score += 20
        required = definition['parameter_raw'] & 65535
        if required == parameter:
            score += 16
        elif required & ~parameter == 0:
            score += 16 - (parameter & ~required).bit_count()
        # Native keeps the earliest definition on equal scores.
        if score > best_score:
            best, best_score = definition, score
    return best
