"""
gesture/features.py - Rotation-Tolerant, Scale-Normalized Hand Feature Extraction
Calculates Euclidean distance ratios, scale-normalized pinch distance, continuous
per-finger extension scores, and palm center coordinates.
Pure math functions; completely independent of camera hardware or GUI.
"""

import math
from typing import Dict, List, Tuple

# Landmark indices
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4

INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8

MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12

RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16

PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20

PALM_MCP_INDICES = [INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]


def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Euclidean distance between two 2D points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def get_hand_scale(landmarks: List[Tuple[float, float]]) -> float:
    """
    Scale reference for the hand: Euclidean distance from Wrist (0) to Middle MCP (9).
    Returns scale in normalized coordinate units (clamped to min 0.05).
    """
    if len(landmarks) < 21:
        return 0.20
    dist = euclidean_distance(landmarks[WRIST], landmarks[MIDDLE_MCP])
    return max(0.05, dist)


def get_palm_center(landmarks: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Calculate palm center as the centroid of the Wrist and four MCP knuckle bases."""
    if len(landmarks) < 21:
        return 0.5, 0.5
    indices = [WRIST] + PALM_MCP_INDICES
    cx = sum(landmarks[i][0] for i in indices) / len(indices)
    cy = sum(landmarks[i][1] for i in indices) / len(indices)
    return cx, cy


def get_normalized_pinch_distance(landmarks: List[Tuple[float, float]]) -> float:
    """
    Pinch distance between Thumb Tip (4) and Index Tip (8),
    normalized by the hand scale (wrist -> middle MCP).
    """
    if len(landmarks) < 21:
        return 1.0
    raw_dist = euclidean_distance(landmarks[THUMB_TIP], landmarks[INDEX_TIP])
    scale = get_hand_scale(landmarks)
    return raw_dist / scale


def get_finger_extension_score(
    landmarks: List[Tuple[float, float]],
    tip_idx: int,
    pip_idx: int,
    mcp_idx: int,
    threshold_ratio: float = 1.55
) -> float:
    """
    Calculate continuous extension score [0.0 to 1.0] for a finger.
    Uses rotation-invariant ratio: dist(tip, mcp) / max(dist(pip, mcp), 0.01).
    """
    if len(landmarks) < 21:
        return 0.0
    tip = landmarks[tip_idx]
    pip = landmarks[pip_idx]
    mcp = landmarks[mcp_idx]

    dist_tip_mcp = euclidean_distance(tip, mcp)
    dist_pip_mcp = max(0.005, euclidean_distance(pip, mcp))
    ratio = dist_tip_mcp / dist_pip_mcp

    # Linear interpolation around threshold_ratio
    # ratio >= threshold_ratio -> score >= 0.8
    # ratio <= 1.0 (curled) -> score ~ 0.0
    min_ratio = 1.05
    max_ratio = threshold_ratio * 1.15
    score = (ratio - min_ratio) / max(0.01, (max_ratio - min_ratio))
    return min(max(score, 0.0), 1.0)


def get_thumb_extension_score(
    landmarks: List[Tuple[float, float]],
    threshold_ratio: float = 1.15
) -> float:
    """
    Calculate continuous extension score [0.0 to 1.0] for the thumb.
    Measures thumb tip distance from pinky MCP relative to thumb IP distance from pinky MCP.
    """
    if len(landmarks) < 21:
        return 0.0
    thumb_tip = landmarks[THUMB_TIP]
    thumb_ip = landmarks[THUMB_IP]
    pinky_mcp = landmarks[PINKY_MCP]

    dist_tip_pinky = euclidean_distance(thumb_tip, pinky_mcp)
    dist_ip_pinky = max(0.005, euclidean_distance(thumb_ip, pinky_mcp))
    ratio = dist_tip_pinky / dist_ip_pinky

    min_ratio = 0.95
    max_ratio = threshold_ratio * 1.20
    score = (ratio - min_ratio) / max(0.01, (max_ratio - min_ratio))
    return min(max(score, 0.0), 1.0)


def analyze_hand_features(
    landmarks: List[Tuple[float, float]],
    finger_extension_ratio: float = 1.55,
    thumb_extension_ratio: float = 1.15,
    pinch_threshold: float = 0.18
) -> Dict:
    """
    Comprehensive feature extraction for a 21-landmark hand.
    Returns dictionary with scale, palm center, normalized pinch distance,
    finger extension scores, and boolean states.
    """
    scale = get_hand_scale(landmarks)
    palm_center = get_palm_center(landmarks)
    pinch_dist = get_normalized_pinch_distance(landmarks)

    # Extension scores
    index_score = get_finger_extension_score(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP, finger_extension_ratio)
    middle_score = get_finger_extension_score(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP, finger_extension_ratio)
    ring_score = get_finger_extension_score(landmarks, RING_TIP, RING_PIP, RING_MCP, finger_extension_ratio)
    pinky_score = get_finger_extension_score(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP, finger_extension_ratio)
    thumb_score = get_thumb_extension_score(landmarks, thumb_extension_ratio)

    # Boolean flags (score >= 0.65 counts as extended)
    ext_cutoff = 0.65
    extended_flags = {
        "thumb": thumb_score >= ext_cutoff,
        "index": index_score >= ext_cutoff,
        "middle": middle_score >= ext_cutoff,
        "ring": ring_score >= ext_cutoff,
        "pinky": pinky_score >= ext_cutoff,
    }

    return {
        "scale": scale,
        "palm_center": palm_center,
        "pinch_distance": pinch_dist,
        "is_pinching": pinch_dist <= pinch_threshold,
        "scores": {
            "thumb": thumb_score,
            "index": index_score,
            "middle": middle_score,
            "ring": ring_score,
            "pinky": pinky_score,
        },
        "extended": extended_flags,
        "num_extended": sum(1 for v in extended_flags.values() if v),
    }
