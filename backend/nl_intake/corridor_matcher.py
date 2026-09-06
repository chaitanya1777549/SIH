"""
Deterministic Corridor Location Matcher for Visakhapatnam (VSKP) - Vijayawada (BZA).
Converts natural-language location descriptions, station names, and kilometer markers
into exact database block_section_id references. Guarantees zero LLM hallucinations.
"""
import re
from typing import Optional, List, Tuple, Dict, Any
from uuid import UUID
from dataclasses import dataclass
from sqlalchemy.orm import Session
from backend.models import BlockSection, Station

# Corridor cumulative station positions from Visakhapatnam (km 0.0) to Vijayawada (km 350.0)
STATION_CATALOG = [
    {"code": "VSKP", "name": "Visakhapatnam", "aliases": ["visakhapatnam", "vizag", "vskp", "waltair"], "seq": 1, "km": 0.0},
    {"code": "DVD", "name": "Duvvada", "aliases": ["duvvada", "dvd"], "seq": 2, "km": 17.0},
    {"code": "AKP", "name": "Anakapalle", "aliases": ["anakapalle", "anakapalli", "akp"], "seq": 3, "km": 33.0},
    {"code": "TUNI", "name": "Tuni", "aliases": ["tuni"], "seq": 4, "km": 96.0},
    {"code": "ANV", "name": "Annavaram", "aliases": ["annavaram", "anv"], "seq": 5, "km": 113.0},
    {"code": "SLO", "name": "Samalkot Junction", "aliases": ["samalkot", "samalkot junction", "samalkot jn", "slo"], "seq": 6, "km": 150.0},
    {"code": "APT", "name": "Anaparti", "aliases": ["anaparti", "anaparthi", "apt"], "seq": 7, "km": 177.0},
    {"code": "RJY", "name": "Rajahmundry", "aliases": ["rajahmundry", "rajamahendravaram", "rjy"], "seq": 8, "km": 200.0},
    {"code": "NDD", "name": "Nidadavolu Junction", "aliases": ["nidadavolu", "nidadavolu jn", "nidadavole", "ndd"], "seq": 9, "km": 223.0},
    {"code": "TDD", "name": "Tadepalligudem", "aliases": ["tadepalligudem", "tdd"], "seq": 10, "km": 242.0},
    {"code": "EE", "name": "Eluru", "aliases": ["eluru", "ee"], "seq": 11, "km": 290.0},
    {"code": "BZA", "name": "Vijayawada Junction", "aliases": ["vijayawada", "vijayawada junction", "bezawada", "bza"], "seq": 12, "km": 350.0},
]

# Section corridor chainage bounds (start_km to end_km along corridor)
CORRIDOR_INTERVALS = [
    ("VSKP", "DVD", 0.0, 17.0),
    ("DVD", "AKP", 17.0, 33.0),
    ("AKP", "TUNI", 33.0, 96.0),
    ("TUNI", "ANV", 96.0, 113.0),
    ("ANV", "SLO", 113.0, 150.0),
    ("SLO", "APT", 150.0, 177.0),
    ("APT", "RJY", 177.0, 200.0),
    ("RJY", "NDD", 200.0, 223.0),
    ("NDD", "TDD", 223.0, 242.0),
    ("TDD", "EE", 242.0, 290.0),
    ("EE", "BZA", 290.0, 350.0),
]

STATION_MAP = {s["code"]: s for s in STATION_CATALOG}

@dataclass
class LocationMatchResult:
    block_section_id: UUID
    section_code: str
    from_station_code: str
    to_station_code: str
    track_code: str
    direction: str
    confidence: float
    match_method: str
    explanation: str
    raw_location_text: str
    alternative_section_id: Optional[UUID] = None
    alternative_section_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_section_id": str(self.block_section_id),
            "section_code": self.section_code,
            "from_station_code": self.from_station_code,
            "to_station_code": self.to_station_code,
            "track_code": self.track_code,
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "match_method": self.match_method,
            "explanation": self.explanation,
            "raw_location_text": self.raw_location_text,
            "alternative_section_id": str(self.alternative_section_id) if self.alternative_section_id else None,
            "alternative_section_code": self.alternative_section_code,
        }


class CorridorLocationMatcher:
    """
    Deterministic rule-based location resolver for the Visakhapatnam-Vijayawada line.
    Matches text to block sections using geometry, chainage, station names, and directional cues.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self._section_cache: Dict[str, BlockSection] = {}
        if db:
            self._load_sections(db)

    def _load_sections(self, db: Session):
        sections = db.query(BlockSection).all()
        for s in sections:
            self._section_cache[s.section_code.upper()] = s

    def get_section_by_code(self, db: Session, section_code: str) -> Optional[BlockSection]:
        norm = section_code.strip().upper()
        if norm in self._section_cache:
            return self._section_cache[norm]
        sec = db.query(BlockSection).filter(BlockSection.section_code.ilike(norm)).first()
        if sec:
            self._section_cache[norm] = sec
        return sec

    def extract_direction(self, text: str) -> Optional[str]:
        """
        Extracts directional orientation: 'DN' (towards Vijayawada) or 'UP' (towards Visakhapatnam).
        """
        text_lower = text.lower()
        
        # Explicit cues
        if re.search(r'\b(dn|down|down line|dn line|dn main|towards vijayawada|towards bezawada|towards bza|southbound)\b', text_lower):
            return "DN"
        if re.search(r'\b(up|up line|up main|towards visakhapatnam|towards vizag|towards vskp|towards waltair|northbound)\b', text_lower):
            return "UP"
        return None

    def extract_chainage_km(self, text: str) -> Optional[float]:
        """
        Extracts kilometer or telegraph post chainage.
        e.g. 'km 52.4', 'kilometer 124', 'km 124/8' (124.8), 'chainage 210'
        """
        # Match 'km 124/8' telegraph post notation
        tp_match = re.search(r'\b(?:km|k\.m\.|kilometer)\s*(\d+)\s*/\s*(\d+)\b', text, re.IGNORECASE)
        if tp_match:
            base_km = float(tp_match.group(1))
            post = float(tp_match.group(2))
            return base_km + (post / 10.0)

        # Match 'km 124.5' or 'km 52' or 'chainage 210'
        km_match = re.search(r'\b(?:km|k\.m\.|kilometer|chainage|ch)\s*[:=]?\s*(\d+(?:\.\d+)?)\b', text, re.IGNORECASE)
        if km_match:
            return float(km_match.group(1))

        # Match standalone number with km suffix: '52km', '124.5 km'
        suffix_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:km|kms|kilometers)\b', text, re.IGNORECASE)
        if suffix_match:
            return float(suffix_match.group(1))

        return None

    def extract_station_mentions(self, text: str) -> List[Dict[str, Any]]:
        """
        Finds all stations mentioned in text, ordered by their appearance position.
        """
        text_lower = text.lower()
        found = []
        
        for stn in STATION_CATALOG:
            matched_alias = None
            earliest_pos = 999999
            
            for alias in stn["aliases"]:
                pattern = rf'\b{re.escape(alias)}\b'
                m = re.search(pattern, text_lower)
                if m and m.start() < earliest_pos:
                    earliest_pos = m.start()
                    matched_alias = alias
                    
            if matched_alias:
                found.append({
                    "station": stn,
                    "pos": earliest_pos,
                    "matched": matched_alias
                })

        found.sort(key=lambda x: x["pos"])
        return [f["station"] for f in found]

    def match_location(self, db: Session, text: str, default_direction: str = "DN") -> LocationMatchResult:
        """
        Deterministically matches input location text to a corridor block section.
        """
        direction = self.extract_direction(text) or default_direction
        chainage_km = self.extract_chainage_km(text)
        stations = self.extract_station_mentions(text)
        
        # 1. Check for direct section code mention (e.g. 'AKP-TUNI-DN' or 'AKP-TUNI')
        code_match = re.search(r'\b([A-Z]{2,4})-([A-Z]{2,4})(?:-(DN|UP))?\b', text.upper())
        if code_match:
            st1, st2, dir_code = code_match.group(1), code_match.group(2), code_match.group(3)
            active_dir = dir_code or direction
            candidate_code = f"{st1}-{st2}-{active_dir}"
            sec = self.get_section_by_code(db, candidate_code)
            if sec:
                alt_dir = "UP" if active_dir == "DN" else "DN"
                alt_code = f"{st2}-{st1}-{alt_dir}" if active_dir == "DN" else f"{st1}-{st2}-{alt_dir}"
                alt_sec = self.get_section_by_code(db, alt_code)
                return LocationMatchResult(
                    block_section_id=sec.id,
                    section_code=sec.section_code,
                    from_station_code=sec.from_station.station_code if sec.from_station else st1,
                    to_station_code=sec.to_station.station_code if sec.to_station else st2,
                    track_code=sec.track.track_code if sec.track else f"{active_dir}_MAIN",
                    direction=active_dir,
                    confidence=1.0,
                    match_method="direct_code",
                    explanation=f"Exact block section code '{candidate_code}' identified in report.",
                    raw_location_text=code_match.group(0),
                    alternative_section_id=alt_sec.id if alt_sec else None,
                    alternative_section_code=alt_sec.section_code if alt_sec else None,
                )

        # 2. Check for Station Pair Mention (e.g. 'between Anakapalle and Tuni')
        if len(stations) >= 2:
            # Check if one of them was preceded by 'towards' (making it a directional destination rather than adjacent station)
            s_primary = stations[0]
            s_secondary = stations[1]
            
            # Find adjacent interval if they are adjacent
            s1, s2 = s_primary, s_secondary
            if s1["seq"] > s2["seq"]:
                s1, s2 = s2, s1
            
            adjacent_interval = None
            for from_stn, to_stn, start_k, end_k in CORRIDOR_INTERVALS:
                if (from_stn == s1["code"] and to_stn == s2["code"]) or (from_stn == s2["code"] and to_stn == s1["code"]):
                    adjacent_interval = (from_stn, to_stn)
                    break
            
            if adjacent_interval:
                from_stn, to_stn = adjacent_interval
                if direction == "DN":
                    target_code = f"{from_stn}-{to_stn}-DN"
                    alt_code = f"{to_stn}-{from_stn}-UP"
                else:
                    target_code = f"{to_stn}-{from_stn}-UP"
                    alt_code = f"{from_stn}-{to_stn}-DN"
                
                sec = self.get_section_by_code(db, target_code)
                alt_sec = self.get_section_by_code(db, alt_code)
                if sec:
                    return LocationMatchResult(
                        block_section_id=sec.id,
                        section_code=sec.section_code,
                        from_station_code=sec.from_station.station_code if sec.from_station else from_stn,
                        to_station_code=sec.to_station.station_code if sec.to_station else to_stn,
                        track_code=sec.track.track_code if sec.track else f"{direction}_MAIN",
                        direction=direction,
                        confidence=0.98,
                        match_method="station_pair",
                        explanation=f"Identified adjacent station pair {s1['name']} ({s1['code']}) and {s2['name']} ({s2['code']}) along {direction} line.",
                        raw_location_text=f"{s1['name']} - {s2['name']}",
                        alternative_section_id=alt_sec.id if alt_sec else None,
                        alternative_section_code=alt_sec.section_code if alt_sec else None,
                    )
            else:
                # Stations mentioned are not directly adjacent (e.g. 'outside Rajahmundry towards Vijayawada')
                # If chainage km is also provided, chainage takes precedence below.
                # If no chainage, match outbound section from the first mentioned station towards the destination
                if chainage_km is None:
                    # Direction determined by sequence order of the two stations
                    computed_dir = "DN" if s_primary["seq"] < s_secondary["seq"] else "UP"
                    active_dir = direction or computed_dir
                    
                    # Find outbound section from s_primary in that direction
                    target_interval = None
                    for from_s, to_s, sk, ek in CORRIDOR_INTERVALS:
                        if active_dir == "DN" and from_s == s_primary["code"]:
                            target_interval = (from_s, to_s)
                            break
                        elif active_dir == "UP" and to_s == s_primary["code"]:
                            target_interval = (to_s, from_s)
                            break

                    if target_interval:
                        target_code = f"{target_interval[0]}-{target_interval[1]}-{active_dir}"
                        alt_code = f"{target_interval[1]}-{target_interval[0]}-{'UP' if active_dir=='DN' else 'DN'}"
                        sec = self.get_section_by_code(db, target_code)
                        alt_sec = self.get_section_by_code(db, alt_code)
                        if sec:
                            return LocationMatchResult(
                                block_section_id=sec.id,
                                section_code=sec.section_code,
                                from_station_code=sec.from_station.station_code if sec.from_station else target_interval[0],
                                to_station_code=sec.to_station.station_code if sec.to_station else target_interval[1],
                                track_code=sec.track.track_code if sec.track else f"{active_dir}_MAIN",
                                direction=active_dir,
                                confidence=0.88,
                                match_method="station_directional_route",
                                explanation=f"Origin {s_primary['name']} heading towards {s_secondary['name']} matched outbound section {target_code}.",
                                raw_location_text=f"{s_primary['name']} -> {s_secondary['name']}",
                                alternative_section_id=alt_sec.id if alt_sec else None,
                                alternative_section_code=alt_sec.section_code if alt_sec else None,
                            )

        # 3. Check for Corridor Kilometer Chainage (e.g. 'km 52.4' or 'kilometer 124')
        if chainage_km is not None:
            # Find which corridor interval contains this chainage
            for from_stn, to_stn, start_k, end_k in CORRIDOR_INTERVALS:
                if start_k <= chainage_km <= end_k:
                    if direction == "DN":
                        target_code = f"{from_stn}-{to_stn}-DN"
                        alt_code = f"{to_stn}-{from_stn}-UP"
                    else:
                        target_code = f"{to_stn}-{from_stn}-UP"
                        alt_code = f"{from_stn}-{to_stn}-DN"
                        
                    sec = self.get_section_by_code(db, target_code)
                    alt_sec = self.get_section_by_code(db, alt_code)
                    if sec:
                        return LocationMatchResult(
                            block_section_id=sec.id,
                            section_code=sec.section_code,
                            from_station_code=sec.from_station.station_code if sec.from_station else from_stn,
                            to_station_code=sec.to_station.station_code if sec.to_station else to_stn,
                            track_code=sec.track.track_code if sec.track else f"{direction}_MAIN",
                            direction=direction,
                            confidence=0.95,
                            match_method="chainage_km",
                            explanation=f"Chainage km {chainage_km} deterministically mapped into corridor interval {from_stn} (km {start_k}) - {to_stn} (km {end_k}) on {direction} track.",
                            raw_location_text=f"km {chainage_km}",
                            alternative_section_id=alt_sec.id if alt_sec else None,
                            alternative_section_code=alt_sec.section_code if alt_sec else None,
                        )

        # 4. Check for Single Station Proximity (e.g. 'near Samalkot' or 'outside Rajahmundry')
        if len(stations) == 1:
            stn = stations[0]
            # Find sections connected to this station
            connected_dn = [c for c in CORRIDOR_INTERVALS if c[0] == stn["code"] or c[1] == stn["code"]]
            if connected_dn:
                match_interval = connected_dn[0]
                if direction == "DN":
                    from_match = [c for c in connected_dn if c[0] == stn["code"]]
                    if from_match:
                        match_interval = from_match[0]
                    target_code = f"{match_interval[0]}-{match_interval[1]}-DN"
                    alt_code = f"{match_interval[1]}-{match_interval[0]}-UP"
                else:
                    to_match = [c for c in connected_dn if c[1] == stn["code"]]
                    if to_match:
                        match_interval = to_match[0]
                    target_code = f"{match_interval[1]}-{match_interval[0]}-UP"
                    alt_code = f"{match_interval[0]}-{match_interval[1]}-DN"

                sec = self.get_section_by_code(db, target_code)
                alt_sec = self.get_section_by_code(db, alt_code)
                if sec:
                    return LocationMatchResult(
                        block_section_id=sec.id,
                        section_code=sec.section_code,
                        from_station_code=sec.from_station.station_code if sec.from_station else match_interval[0],
                        to_station_code=sec.to_station.station_code if sec.to_station else match_interval[1],
                        track_code=sec.track.track_code if sec.track else f"{direction}_MAIN",
                        direction=direction,
                        confidence=0.85,
                        match_method="station_proximity",
                        explanation=f"Station reference '{stn['name']}' resolved to adjacent section {target_code} ({direction} line).",
                        raw_location_text=stn["name"],
                        alternative_section_id=alt_sec.id if alt_sec else None,
                        alternative_section_code=alt_sec.section_code if alt_sec else None,
                    )

        # 5. Fallback default: First major section (VSKP-DVD-DN) with low confidence
        fallback_sec = self.get_section_by_code(db, "VSKP-DVD-DN")
        if not fallback_sec:
            fallback_sec = db.query(BlockSection).first()
            
        return LocationMatchResult(
            block_section_id=fallback_sec.id,
            section_code=fallback_sec.section_code,
            from_station_code=fallback_sec.from_station.station_code if fallback_sec.from_station else "VSKP",
            to_station_code=fallback_sec.to_station.station_code if fallback_sec.to_station else "DVD",
            track_code=fallback_sec.track.track_code if fallback_sec.track else "DN_MAIN",
            direction="DN",
            confidence=0.30,
            match_method="corridor_default_fallback",
            explanation="Could not unambiguously extract corridor location; defaulted to corridor entry section VSKP-DVD-DN.",
            raw_location_text=text[:50],
        )
