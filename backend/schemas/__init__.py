from backend.schemas.auth import AdminLoginRequest, AdminLoginResponse, AdminCreateRequest, AdminResponse
from backend.schemas.voter import VoterScanRequest, VoterFaceVerifyRequest, OTPSendRequest, OTPVerifyRequest, VoterResponse
from backend.schemas.vote import VoteCastRequest, VoteCastResponse, BallotRequest, BallotResponse, TallyResponse
from backend.schemas.uncontested import UncontestedDeclareRequest, UncontestedReverseRequest, UncontestedConstituencyResponse
from backend.schemas.admin import BoothCreateRequest, WorkerCreateRequest, AnomalyEventResponse, DashboardStatsResponse
