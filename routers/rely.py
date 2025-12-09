from __future__ import annotations

import asyncio
import hmac
import traceback
from dataclasses import dataclass
from functools import wraps
from typing import List, Optional, Tuple, cast, Dict, Callable, TypeVar, Awaitable
from decimal import Decimal

from loguru import logger
from quart import Blueprint, request, jsonify, abort, Response
from stellar_sdk import ServerAsync, AiohttpClient
from stellar_sdk.exceptions import SdkError

from other.config_reader import config
from other.grist_tools import grist_manager, GristTableConfig, GristAPI
from other.stellar_tools import stellar_build_xdr, add_transaction
from other.telegram_tools import send_telegram_message_


class HolderNotFoundException(Exception):
    """Custom exception raised when a Grist holder record cannot be found."""
    pass


RELY_DEAL_CHAT_ID = -1003363491610  # rely
# RELY_DEAL_CHAT_ID = -1001767165598 #test group

GRIST_ACCESS_ID = "kceNjvoEEihSsc8dQ5vZVB"
GRIST_BASE_URL = "https://mtl-rely.getgrist.com/api/docs"

DEAL_ACCOUNT = "GCWCVYBHVDBZP7U4DDJBPEMWKYMUQDR6PKWS6EHYM2OB4YSZGBU3DEAL"
DEAL_ASSET = "RELY-GC5WBT3D5GPZ3FU7MTUMVWTLAS3IUU7EPCTFJSLHI5RYMPTLEIX2RELY"

# --- Concurrency Lock ---
deal_locks: Dict[int, asyncio.Lock] = {}

# --- Typing for Decorator ---
F = TypeVar('F', bound=Callable[..., Awaitable[Tuple[Response, int]]])


def _get_deal_lock(deal_id: int) -> asyncio.Lock:
    """
    Retrieves or creates a lock for a given deal ID.

    This mechanism prevents race conditions when multiple webhooks for the
    same deal are received concurrently.

    Args:
        deal_id: The unique identifier for the deal.

    Returns:
        An asyncio.Lock instance specific to the deal ID.
    """
    if deal_id not in deal_locks:
        deal_locks[deal_id] = asyncio.Lock()
    return deal_locks[deal_id]


def require_grist_auth(f: F) -> F:
    """
    A decorator to verify Grist webhook signature.

    It checks for a Bearer token in the Authorization header and validates it
    against the configured Grist income token using a secure HMAC comparison.

    Args:
        f: The async function to decorate.

    Returns:
        The decorated async function.
    """

    @wraps(f)
    async def decorated_function(*args, **kwargs) -> Tuple[Response, int]:
        """Wrapper that performs authentication before calling the original function."""
        ip = request.remote_addr
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            logger.warning(f"Grist webhook from {ip}: Authorization header is missing.")
            abort(401, "Authorization header is missing")

        token = auth_header.strip()
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
        if not hmac.compare_digest(token.encode(), config.grist_income.encode()):
            logger.warning(f"Grist webhook from {ip}: Invalid token provided: '{token}'")
            abort(403, "Invalid token")

        return await f(*args, **kwargs)

    return cast(F, decorated_function)


@dataclass
class DealRecord:
    """Represents a single deal record from the Grist 'Deals' table."""
    id: int
    checked: bool
    transaction: Optional[str]


@dataclass
class DealParticipant:
    """Represents an assembled participant of a deal with their details."""
    id: int
    amount: Decimal
    stellar: str
    tg_username: Optional[str]

    @property
    def display_name(self) -> str:
        """Returns a user-friendly identifier for the participant."""
        return self.tg_username or f"Participant ID:{self.id}"


@dataclass
class DealParticipantEntry:
    """Represents a participant entry from the Grist 'Conditions' table."""
    id: int
    deal_id: int
    holder_id: int
    amount: Decimal


@dataclass
class HolderEntry:
    """Represents a holder's record from the Grist 'Holders' table."""
    id: int
    stellar: Optional[str]
    telegram: Optional[str]


class GristDealParticipantRepository:
    """
    Repository for managing participant entries in deals.

    Handles read operations for participant contributions stored in the
    Grist 'Conditions' table.
    """

    def __init__(self, grist_api: GristAPI):
        """
        Initialize the repository with Grist configuration for the Conditions table.

        Args:
            grist_api: An instance of the GristAPI client.
        """
        self._grist_api = grist_api
        self._table_config = GristTableConfig(
            access_id=GRIST_ACCESS_ID,
            table_name="Conditions",
            base_url=GRIST_BASE_URL,
        )

    async def get_participants_by_deal_id(self, deal_id: int) -> List[DealParticipantEntry]:
        """
        Retrieve all participants for a specific deal.

        Args:
            deal_id: The ID of the deal.

        Returns:
            A list of DealParticipantEntry objects.
        """
        try:
            records = await self._grist_api.fetch_data(
                table=self._table_config,
                filter_dict={"Deal": [deal_id]}
            )
        except Exception as e:
            logger.error(f"Failed to fetch participants for deal {deal_id} from Grist: {e}\n{traceback.format_exc()}")
            return []

        participants = []
        for record in records:
            try:
                participants.append(DealParticipantEntry(
                    id=record["id"],
                    deal_id=record["Deal"],
                    holder_id=record["Participant"],
                    amount=Decimal(str(record["Amount"]))
                ))
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Skipping malformed participant record for deal {deal_id}: {record}. Error: {e}")

        return participants


class GristHolderRepository:
    """
    Repository for managing holder entries in Grist.
    """
    def __init__(self, grist_api: GristAPI):
        """
        Initialize the repository with Grist configuration for the Holders table.

        Args:
            grist_api: An instance of the GristAPI client.
        """
        self._grist_api = grist_api
        self._table_config = GristTableConfig(
            access_id=GRIST_ACCESS_ID,
            table_name="Holders",
            base_url=GRIST_BASE_URL,
        )

    async def get_holders_by_ids(self, holder_ids: List[int]) -> Dict[int, HolderEntry]:
        """
        Retrieve holders by their IDs.

        Args:
            holder_ids: A list of holder IDs.

        Returns:
            A dictionary mapping holder IDs to HolderEntry objects.
        """
        if not holder_ids:
            return {}

        try:
            records = await self._grist_api.fetch_data(
                table=self._table_config,
                filter_dict={"id": holder_ids}
            )
        except Exception as e:
            logger.error(f"Failed to fetch holders by IDs {holder_ids} from Grist: {e}\n{traceback.format_exc()}")
            return {}

        holders = {}
        for record in records:
            try:
                holders[record['id']] = HolderEntry(
                    id=record['id'],
                    stellar=record.get('Stellar'),
                    telegram=record.get('Telegram')
                )
            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping malformed holder record: {record}. Error: {e}")
        return holders


class GristDealRepository:
    """
    Repository for managing deal records in Grist.
    """

    def __init__(self, grist_api: GristAPI):
        """
        Initialize the repository with Grist configuration for the Deals table.

        Args:
            grist_api: An instance of the GristAPI client.
        """
        self._grist_api = grist_api
        self._table_config = GristTableConfig(
            access_id=GRIST_ACCESS_ID,
            table_name="Deals",
            base_url=GRIST_BASE_URL,
        )

    async def set_transaction(self, deal_id: int, transaction_url: str) -> None:
        """
        Sets the transaction URL for a specific deal in Grist.

        Args:
            deal_id: The ID of the deal to update.
            transaction_url: The URL of the transaction to set.
        """
        try:
            await self._grist_api.patch_data(self._table_config, {
                "records": [{"id": deal_id, "fields": {"Transaction": transaction_url}}]
            })
            logger.info(f"Successfully set transaction URL for deal {deal_id}.")
        except Exception as e:
            logger.error(f"Failed to set transaction URL for deal {deal_id}: {e}\n{traceback.format_exc()}")

    async def disable_checked(self, deal_id: int) -> None:
        """
        Disables the 'Checked' status for a specific deal in Grist.

        This is typically used when a deal fails validation.

        Args:
            deal_id: The ID of the deal to update.
        """
        try:
            await self._grist_api.patch_data(self._table_config, {
                "records": [{"id": deal_id, "fields": {"Checked": False}}]
            })
            logger.info(f"Successfully disabled 'Checked' status for deal {deal_id}.")
        except Exception as e:
            logger.error(f"Failed to disable 'Checked' status for deal {deal_id}: {e}\n{traceback.format_exc()}")


# --- Module-level Repository Instantiation ---
participant_repo = GristDealParticipantRepository(grist_manager)
holder_repo = GristHolderRepository(grist_manager)
deal_repo = GristDealRepository(grist_manager)


class Deal:
    """
    Represents a Deal aggregate root, encapsulating the business logic for processing a deal.
    """

    def __init__(self, deal_record: DealRecord):
        """
        Initializes the Deal aggregate.

        Args:
            deal_record: The raw deal record from Grist.
        """
        self.deal_record = deal_record
        self.participants: List[DealParticipant] = []

    async def _load_participants(self) -> None:
        """
        Loads and assembles participant objects for the deal from the repositories.
        """
        logger.info(f"Loading participants for deal {self.deal_record.id}.")
        participant_entries = await participant_repo.get_participants_by_deal_id(self.deal_record.id)
        if not participant_entries:
            logger.info(f"No participants found for deal {self.deal_record.id}.")
            return

        holder_ids = [p.holder_id for p in participant_entries]
        holders = await holder_repo.get_holders_by_ids(holder_ids)

        assembled_participants = []
        for p_entry in participant_entries:
            holder = holders.get(p_entry.holder_id)
            if holder:
                assembled_participants.append(DealParticipant(
                    id=p_entry.id,
                    amount=p_entry.amount,
                    stellar=holder.stellar,
                    tg_username=holder.telegram
                ))
            else:
                error_msg = f"Participant ID:{p_entry.id} is missing holder with ID {p_entry.holder_id} for deal {self.deal_record.id}"
                logger.error(error_msg)
                raise HolderNotFoundException(error_msg)

        self.participants = assembled_participants
        logger.info(f"Loaded and assembled {len(self.participants)} participants for deal {self.deal_record.id}.")

    def _validate_preconditions(self) -> List[str]:
        """
        Validates that the deal meets the preconditions for processing.

        Returns:
            A list of error strings. An empty list signifies success.
        """
        errors = []
        if not self.participants:
            errors.append(f"Deal {self.deal_record.id} has no participants.")
            return errors

        for p in self.participants:
            if not p.stellar:
                errors.append(f"Участник {p.display_name} в сделке {self.deal_record.id} не имеет stellar адреса.")
            if p.amount < Decimal("0.1"):
                errors.append(f"Участник {p.display_name} в сделке {self.deal_record.id} имеет сумму {p.amount}, что меньше 0.1.")
        return errors

    async def _build_transaction(self) -> str:
        """
        Builds a Stellar transaction XDR based on the deal's participants.

        Returns:
            A base64-encoded XDR string representing the transaction.
        """
        operations = [
            {
                'type': 'payment',
                'destination': DEAL_ACCOUNT,
                'asset': DEAL_ASSET,
                'amount': str(p.amount),
                'sourceAccount': p.stellar
            } for p in self.participants
        ]
        memo_text = f"Deal #{self.deal_record.id}"

        async with ServerAsync(horizon_url="https://horizon.stellar.org", client=AiohttpClient()) as server:
            source_account = await server.load_account(DEAL_ACCOUNT)

        tx_data = {
            'publicKey': DEAL_ACCOUNT,
            'sequence': str(source_account.sequence + 1),
            'memo': memo_text,
            'memo_type': 'memo_text',
            'operations': operations
        }
        # The return type of stellar_build_xdr is not specific enough, hence the cast.
        return cast(str, await stellar_build_xdr(tx_data))

    async def process_transaction_creation(self) -> Tuple[bool, List[str] | str]:
        """
        Orchestrates loading, validation, and transaction creation for the deal.

        This is the main entry point for processing the business logic of the deal.

        Returns:
            A tuple of (success, result), where `result` is a list of error
            strings on failure, or the transaction XDR string on success.
        """
        try:
            await self._load_participants()
        except HolderNotFoundException as e:
            return False, [str(e)]
        validation_errors = self._validate_preconditions()
        if validation_errors:
            return False, validation_errors

        logger.info(f"Deal {self.deal_record.id} passed precondition validation.")
        try:
            xdr = await self._build_transaction()
            logger.info(f"Built transaction for deal {self.deal_record.id}: {xdr}")
            return True, xdr
        except SdkError as e:
            logger.error(f"Stellar SDK error while building transaction for deal {self.deal_record.id}: {e}")
            return False, ["Stellar SDK error. Check logs for details."]
        except Exception as e:
            logger.error(f"Unexpected error building transaction for deal {self.deal_record.id}: {e}\n{traceback.format_exc()}")
            return False, ["Unexpected error. Check logs for details."]


async def _handle_checked_empty_transaction(deal_record: DealRecord) -> None:
    """
    Handles the core logic for a deal that is 'Checked' but has no transaction.

    It acquires a lock, processes the deal, and handles success or failure by
    updating Grist and sending Telegram notifications.

    Args:
        deal_record: The deal record to process.
    """
    deal_id = deal_record.id
    lock = _get_deal_lock(deal_id)

    async with lock:
        logger.info(f"Processing deal {deal_id}: {deal_record}")
        deal_aggregate = Deal(deal_record)
        success, result = await deal_aggregate.process_transaction_creation()

        if not success:
            errors = result
            logger.warning(f"Deal {deal_id} failed validation with errors: {errors}")
            await deal_repo.disable_checked(deal_id)
            errors_str = '\n'.join([f"- {e}" for e in errors])
            text = (f"Проверка сделки #{deal_id} провалена. Ошибки:\n{errors_str}\n"
                    f"Автоматическое создание транзакции отменено.")
            await send_telegram_message_(RELY_DEAL_CHAT_ID, text)
            return

        xdr = result
        add_success, add_result = await add_transaction(xdr, f"Rely deal #{deal_id}")
        if add_success:
            transaction_url = f"https://eurmtl.me/sign_tools/{add_result}"
            logger.info(f"Transaction for deal {deal_id} added with hash {add_result}. URL: {transaction_url}")
            await deal_repo.set_transaction(deal_id, transaction_url)
            text = f'Создана транзакция для сделки #{deal_id}. <a href="{transaction_url}">URL</a>'
            await send_telegram_message_(RELY_DEAL_CHAT_ID, text)
        else:
            logger.error(f"Failed to add transaction for deal {deal_id}: {add_result}")
            await send_telegram_message_(RELY_DEAL_CHAT_ID, f"Ошибка добавления транзакции для сделки #{deal_id}. Детали: {add_result}")


async def _process_grist_payload(payload: List[Dict]) -> None:
    """
    Processes the Grist webhook payload, creating tasks to handle valid deals.

    It iterates through records, identifies deals that need processing,
    and creates background tasks for them.

    Args:
        payload: The JSON payload (list of records) from the Grist webhook.
    """
    if not isinstance(payload, list):
        logger.warning(f"Webhook payload is not a list, skipping: {payload}")
        return

    for item in payload:
        try:
            record = DealRecord(id=item['id'], checked=item.get('Checked', False), transaction=item.get('Transaction'))
            if record.checked and not record.transaction:
                asyncio.create_task(_handle_checked_empty_transaction(record))
        except (KeyError, TypeError) as e:
            logger.warning(f"Could not process record, skipping: {item}. Error: {e}")

    logger.info(f"Grist webhook payload processing initiated for {len(payload)} records.")


blueprint = Blueprint('rely', __name__)


@blueprint.route('/rely/grist-webhook', methods=['POST', 'GET'])
@require_grist_auth
async def grist_webhook() -> tuple[Response, int]:
    """
    Endpoint to receive a webhook from Grist.

    Authenticates the request, then processes the payload in the background.
    """
    try:
        payload = await request.get_json()
    except Exception:
        abort(400, "Invalid JSON payload")

    asyncio.create_task(_process_grist_payload(payload))

    return jsonify({"status": "ok"}), 200


