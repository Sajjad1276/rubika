import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ad_network.core.models import Base, ChannelStatus, ListNetwork, RegistrationSource, RegistrationStatus, User
from ad_network.core.services import ListService, RegistrationService, ViolationService


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_registration_approval_activates_channel_and_assigns_monotonic_code(session):
    user = User(rubika_user_id="u1", display_name="Owner")
    network = ListNetwork(code="L01", name="Test List")
    session.add_all([user, network])
    await session.flush()

    service = RegistrationService(session)
    request = await service.start(
        rubika_guid="c1",
        applicant=user,
        source=RegistrationSource.SELF,
        list_id=network.id,
    )
    await service.submit_for_verification(request)
    await service.verify(request, approved=True, verifier_id=user.id, member_count=250)

    assert request.status == RegistrationStatus.ACTIVE
    channel = await session.get(__import__("ad_network.core.models", fromlist=["Channel"]).Channel, request.channel_id)
    assert channel.status == ChannelStatus.ACTIVE
    assert channel.list_code == "#001"
    assert channel.member_count == 250

    code = await ListService(session).allocate_channel_code(network.id)
    assert code == "#002"


@pytest.mark.asyncio
async def test_violation_is_persisted(session):
    user = User(rubika_user_id="u2")
    channel = __import__("ad_network.core.models", fromlist=["Channel"]).Channel(rubika_guid="c2")
    session.add_all([user, channel])
    await session.flush()

    violation = await ViolationService(session).record(
        channel_id=channel.id,
        admin_id=user.id,
        violation_type="early_ad_deletion",
        severity=2,
    )
    assert violation.severity == 2
