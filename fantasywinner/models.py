from dataclasses import dataclass
from typing import Optional

# Typical week-to-week standard deviation of PPR points by position, used when
# a source gives only a point projection and no floor/ceiling.
DEFAULT_SD = {"QB": 7.0, "RB": 6.0, "WR": 6.5, "TE": 5.0, "K": 3.5, "DST": 4.5}

UNAVAILABLE = {"OUT", "IR", "BYE", "SUSPENDED"}


@dataclass
class Player:
    name: str
    pos: str  # QB RB WR TE K DST
    team: str
    proj: float  # projected PPR points for the week
    status: str = "ACTIVE"  # ACTIVE QUESTIONABLE DOUBTFUL OUT IR BYE
    opp: str = ""
    sd: Optional[float] = None  # weekly std dev of points
    slot: str = ""  # current ESPN slot (QB, RB, FLEX, BE, IR ...)
    trend: float = 0.0  # recent % change in ownership (waiver buzz)

    @property
    def stdev(self) -> float:
        return self.sd if self.sd is not None else DEFAULT_SD.get(self.pos, 5.0)

    @property
    def available(self) -> bool:
        return self.status.upper() not in UNAVAILABLE

    @property
    def floor(self) -> float:
        return max(0.0, self.proj - 1.28 * self.stdev)

    @property
    def ceiling(self) -> float:
        return self.proj + 1.28 * self.stdev
