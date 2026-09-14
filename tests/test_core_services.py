import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ad_network.core.commerce import CommerceService, PaymentStatus, PriceRule
from ad_network.core.config import Settings
from ad_network.core.models import (
    Base,
    Channel,
    ChannelStatus,
    ListNetwork,
    RegistrationSource,
    RegistrationStatus,
    User,
    UserRole,
)
from ad_network.core.roles import RoleService
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

    channel = await session.get(Channel, request.channel_id)
    channel.access_verified = True
    channel.can_send = True
    channel.can_edit = True
    channel.can_delete = True
    await session.flush()

    await service.verify(request, approved=True, verifier_id=user.id, member_count=250)

    assert request.status == RegistrationStatus.ACTIVE
    channel = await session.get(Channel, request.channel_id)
    assert channel.status == ChannelStatus.ACTIVE
    assert channel.list_code == "#001"
    assert channel.member_count == 250

    code = await ListService(session).allocate_channel_code(network.id)
    assert code == "#002"


@pytest.mark.asyncio
async def test_registration_approval_fails_without_verified_permissions(session):
    user = User(rubika_user_id="u-perm")
    network = ListNetwork(code="L02", name="Permission List")
    session.add_all([user, network])
    await session.flush()

    service = RegistrationService(session)
    request = await service.start(
        rubika_guid="c-perm",
        applicant=user,
        source=RegistrationSource.SELF,
        list_id=network.id,
    )
    await service.submit_for_verification(request)

    with pytest.raises(ValueError, match="permissions"):
        await service.verify(request, approved=True, verifier_id=user.id)


@pytest.mark.asyncio
async def test_violation_is_persisted(session):
    user = User(rubika_user_id="u2")
    channel = Channel(rubika_guid="c2")
    session.add_all([user, channel])
    await session.flush()

    violation = await ViolationService(session).record(
        channel_id=channel.id,
        admin_id=user.id,
        violation_type="early_ad_deletion",
        severity=2,
    )
    assert violation.severity == 2


@pytest.mark.asyncio
async def test_role_service_uses_configured_usernames_and_persisted_supervisor_role(session):
    settings = Settings(owner_username="Owner_User", admin_username="Admin_User")
    owner = User(rubika_user_id="u-owner", username="@OWNER_USER", roles_json='["user"]')
    admin = User(rubika_user_id="u-admin", username="admin_user", roles_json='["user"]')
    supervisor = User(rubika_user_id="u-super", username="other", roles_json='["user", "supervisor"]')
    impostor = User(rubika_user_id="u-impostor", username="not-owner", roles_json='["owner"]')
    session.add_all([owner, admin, supervisor, impostor])
    await session.flush()
    service = RoleService(session, settings)

    assert service.has(owner, UserRole.OWNER)
    assert service.has(admin, UserRole.ADMIN)
    assert service.has(supervisor, UserRole.SUPERVISOR)
    assert not service.has(impostor, UserRole.OWNER)


@pytest.mark.asyncio
async def test_commerce_quote_and_payment_are_idempotent(session):
    user = User(rubika_user_id="u-commerce")
    network = ListNetwork(code="L03", name="Commerce List")
    session.add_all([user, network])
    await session.flush()
    session.add(PriceRule(
        list_id=network.id,
        title="Base",
        min_channels=1,
        price_per_channel=50_000,
        retention_hours=6,
    ))
    await session.flush()

    service = CommerceService(session)
    unit, total = await service.quote(list_id=network.id, channel_count=3, retention_hours=6)
    assert (unit, total) == (50_000, 150_000)

    order = await service.create_order(
        advertiser=user,
        title="Campaign",
        content_ref="c-source:m1",
        list_id=network.id,
        channel_count=3,
        retention_hours=6,
    )
    payment_a = await service.create_payment(order.id)
    payment_b = await service.create_payment(order.id)
    assert payment_a.id == payment_b.id
    assert payment_a.status == PaymentStatus.PENDING
