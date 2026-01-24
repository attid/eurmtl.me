from __future__ import annotations

import asyncio
import hmac
import re
import traceback
from dataclasses import dataclass
from functools import wraps
from typing import (
    cast,
    Callable,
    TypeVar,
    Awaitable,
    Any,
)
from decimal import Decimal

from aiogram.exceptions import TelegramBadRequest
from loguru import logger
from quart import Blueprint, request, jsonify, abort, Response
from stellar_sdk.server_async import ServerAsync
from stellar_sdk.client.aiohttp_client import AiohttpClient
from stellar_sdk.exceptions import SdkError

from other.config_reader import config
from other.grist_tools import grist_manager, GristTableConfig, GristAPI
from services.stellar_client import stellar_build_xdr, add_transaction
from other.telegram_tools import skynet_bot


RELY_DEAL_CHAT_ID = -1003363491610  # rely
# RELY_DEAL_CHAT_ID = -1001767165598 #test group

GRIST_ACCESS_ID = "kceNjvoEEihSsc8dQ5vZVB"
GRIST_BASE_URL = "https://mtl-rely.getgrist.com/api/docs"

DEAL_ACCOUNT = "GCWCVYBHVDBZP7U4DDJBPEMWKYMUQDR6PKWS6EHYM2OB4YSZGBU3DEAL"
DEAL_ASSET = "RELY-GC5WBT3D5GPZ3FU7MTUMVWTLAS3IUU7EPCTFJSLHI5RYMPTLEIX2RELY"
RELY_ACCOUNT = "GC5WBT3D5GPZ3FU7MTUMVWTLAS3IUU7EPCTFJSLHI5RYMPTLEIX2RELY"

# --- Concurrency Lock ---
deal_locks: dict[int, asyncio.Lock] = {}

# --- Typing for Decorator ---
F = TypeVar("F", bound=Callable[..., Awaitable[tuple[Response, int]]])


class TelegramMessenger:
    """A helper class to send messages to a specific Telegram chat."""

    @staticmethod
    def parse_tg_url(
        url: str | None,
    ) -> tuple[int | str | None, int | None]:
        """
        Parses a Telegram message URL to extract chat_id and message_id.

        Args:
            url: The Telegram message URL.

        Returns:
            A tuple of (chat_id, message_id).
        """
        if not url:
            return None, None

        # Private chat link: t.me/c/CHAT_ID/MSG_ID
        private_match = re.search(r"t\.me/c/(\d+)/(\d+)", url)
        if private_match:
            chat_id = int("-100" + private_match.group(1))
            message_id = int(private_match.group(2))
            return chat_id, message_id

        # Public chat link: t.me/USERNAME/MSG_ID
        public_match = re.search(r"t\.me/([\w_]+)/(\d+)", url)
        if public_match:
            chat_id = public_match.group(1)
            message_id = int(public_match.group(2))
            return chat_id, message_id

        return None, None

    @staticmethod
    async def send_message(
        text: str,
        chat_id: int | str | None = None,
        reply_to_message_id: int | None = None,
        disable_web_page_preview: bool = True,
        parse_mode: str = "HTML",
    ) -> None:
        """
        Sends a message to a Telegram chat.

        Args:
            text: The message text to send.
            chat_id: The ID of the chat to send the message to. Defaults to RELY_DEAL_CHAT_ID.
            reply_to_message_id: If provided, the message will be a reply to this ID.
            disable_web_page_preview: If True, disables web page previews for links.
            parse_mode: The parse mode for the message text (e.g., 'HTML', 'Markdown').
        """
        await skynet_bot.send_message(
            chat_id=chat_id or RELY_DEAL_CHAT_ID,
            text=text,
            reply_to_message_id=reply_to_message_id,
            disable_web_page_preview=disable_web_page_preview,
            parse_mode=parse_mode,
        )


class HolderNotFoundException(Exception):
    """Custom exception raised when a Grist holder record cannot be found."""

    pass


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
    async def decorated_function(*args, **kwargs) -> tuple[Response, int]:
        """Wrapper that performs authentication before calling the original function."""
        ip = request.remote_addr
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.warning(f"Grist webhook from {ip}: Authorization header is missing.")
            abort(401, "Authorization header is missing")

        auth_header = cast(str, auth_header)
        token = auth_header.strip()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        if not hmac.compare_digest(token.encode(), config.grist_income.encode()):
            logger.warning(
                f"Grist webhook from {ip}: Invalid token provided: '{token}'"
            )
            abort(403, "Invalid token")

        return await f(*args, **kwargs)

    return cast(F, decorated_function)


@dataclass(frozen=True, slots=True)
class DealRecord:
    """Represents a single deal record from the Grist 'Deals' table."""

    id: int
    checked: bool
    result_checked: bool
    transaction: str | None = None
    message_url: str | None = None
    result_transaction: str | None = None


@dataclass(frozen=True, slots=True)
class DealParticipant:
    """Represents an assembled participant of a deal with their details."""

    id: int
    amount: Decimal
    is_done: bool
    stellar: str | None
    tg_username: str | None

    @property
    def display_name(self) -> str:
        """Returns a user-friendly identifier for the participant."""
        if self.tg_username:
            username = self.tg_username.strip()
            if not username.startswith("@"):
                return f"@{username}"
            return username
        return f"Participant ID:{self.id}"


@dataclass(frozen=True, slots=True)
class DealParticipantEntry:
    """Represents a participant entry from the Grist 'Conditions' table."""

    id: int
    deal_id: int
    holder_id: int
    amount: Decimal
    is_done: bool


@dataclass(frozen=True, slots=True)
class HolderEntry:
    """Represents a holder's record from the Grist 'Holders' table."""

    id: int
    stellar: str | None
    telegram: str | None


@dataclass(frozen=True, slots=True)
class TransactionProcessResult:
    """The result of a deal transaction process."""

    success: bool
    xdr: str | None = None
    errors: list[str] | None = None


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

    async def get_participants_by_deal_id(
        self, deal_id: int
    ) -> list[DealParticipantEntry]:
        """
        Retrieve all participants for a specific deal.

        Args:
            deal_id: The ID of the deal.

        Returns:
            A list of DealParticipantEntry objects.
        """
        try:
            records = await self._grist_api.fetch_data(
                table=self._table_config, filter_dict={"Deal": [deal_id]}
            )
        except Exception as e:
            logger.error(
                f"Failed to fetch participants for deal {deal_id} from Grist: {e}\n{traceback.format_exc()}"
            )
            return []

        participants = []
        for record in records:
            try:
                participants.append(
                    DealParticipantEntry(
                        id=record["id"],
                        deal_id=record["Deal"],
                        holder_id=record["Participant"],
                        amount=Decimal(str(record["Amount"])),
                        is_done=record["Done"],
                    )
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(
                    f"Skipping malformed participant record for deal {deal_id}: {record}. Error: {e}"
                )

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

    async def get_holders_by_ids(self, holder_ids: list[int]) -> dict[int, HolderEntry]:
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
                table=self._table_config, filter_dict={"id": holder_ids}
            )
        except Exception as e:
            logger.error(
                f"Failed to fetch holders by IDs {holder_ids} from Grist: {e}\n{traceback.format_exc()}"
            )
            return {}

        holders = {}
        for record in records:
            try:
                holders[record["id"]] = HolderEntry(
                    id=record["id"],
                    stellar=record.get("Stellar"),
                    telegram=record.get("Telegram"),
                )
            except (KeyError, TypeError) as e:
                logger.warning(
                    f"Skipping malformed holder record: {record}. Error: {e}"
                )
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

    async def update_fields(self, deal_id: int, fields: dict[str, Any]) -> bool:
        """
        Updates specific fields for a deal in Grist.

        Args:
            deal_id: The ID of the deal to update.
            fields: A dictionary of fields to update.

        Returns:
            True if update was successful, False otherwise.
        """
        try:
            await self._grist_api.patch_data(
                self._table_config,
                {"records": [{"id": deal_id, "fields": fields}]},
            )
            logger.info(f"Successfully updated fields for deal {deal_id}: {fields}")
            return True
        except Exception as e:
            logger.error(
                f"Failed to update fields for deal {deal_id}: {e}\n{traceback.format_exc()}"
            )
            return False


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
        self.participants: list[DealParticipant] = []

    @property
    def mention_string(self) -> str:
        """Returns a comma-separated string of participant mentions."""
        return ", ".join(p.display_name for p in self.participants)

    async def _load_participants(self) -> None:
        """
        Loads and assembles participant objects for the deal from the repositories.
        """
        logger.info(f"Loading participants for deal {self.deal_record.id}.")
        participant_entries = await participant_repo.get_participants_by_deal_id(
            self.deal_record.id
        )
        if not participant_entries:
            logger.info(f"No participants found for deal {self.deal_record.id}.")
            return

        holder_ids = [p.holder_id for p in participant_entries]
        holders = await holder_repo.get_holders_by_ids(holder_ids)

        assembled_participants = []
        for p_entry in participant_entries:
            holder = holders.get(p_entry.holder_id)
            if holder:
                assembled_participants.append(
                    DealParticipant(
                        id=p_entry.id,
                        amount=p_entry.amount,
                        stellar=holder.stellar,
                        tg_username=holder.telegram,
                        is_done=p_entry.is_done,
                    )
                )
            else:
                error_msg = f"Participant ID:{p_entry.id} is missing holder with ID {p_entry.holder_id} for deal {self.deal_record.id}"
                logger.error(error_msg)
                raise HolderNotFoundException(error_msg)

        self.participants = assembled_participants
        logger.info(
            f"Loaded and assembled {len(self.participants)} participants for deal {self.deal_record.id}."
        )

    def _validate_preconditions(self) -> list[str]:
        """
        Validates that the deal meets the preconditions for processing.

        Returns:
            A list of error strings. An empty list signifies success.
        """
        errors = []
        if not self.participants:
            errors.append(f"❌ В сделке {self.deal_record.id} отсутствуют участники.")
            return errors

        for p in self.participants:
            if not p.stellar:
                errors.append(
                    f"⚠️ Участник {p.display_name} в сделке {self.deal_record.id} не имеет stellar адреса."
                )
            if p.amount < Decimal("0.1"):
                errors.append(
                    f"⚠️ Участник {p.display_name} в сделке {self.deal_record.id} имеет сумму {p.amount}, что меньше 0.1."
                )
        return errors

    async def _build_envelope(self, operations: list[dict[str, Any]], memo: str) -> str:
        """
        Helper method to build a Stellar transaction envelope.

        Args:
            operations: A list of operation dictionaries.
            memo: The memo text for the transaction.

        Returns:
            A base64-encoded XDR string.
        """
        async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            source_account = await server.load_account(DEAL_ACCOUNT)

        tx_data = {
            "publicKey": DEAL_ACCOUNT,
            "sequence": str(source_account.sequence + 1),
            "memo": memo,
            "memo_type": "memo_text",
            "operations": operations,
        }
        # The return type of stellar_build_xdr is not specific enough, hence the cast.
        return cast(str, await stellar_build_xdr(tx_data))

    async def _build_transaction(self) -> str:
        """
        Builds a Stellar transaction XDR based on the deal's participants.

        Returns:
            A base64-encoded XDR string representing the transaction.
        """
        operations = [
            {
                "type": "payment",
                "destination": DEAL_ACCOUNT,
                "asset": DEAL_ASSET,
                "amount": str(p.amount),
                "sourceAccount": p.stellar,
            }
            for p in self.participants
        ]
        memo_text = f"Deal #{self.deal_record.id}"
        return await self._build_envelope(operations, memo_text)

    async def _build_result_transaction(self) -> str:
        """
        Builds a Stellar transaction XDR based on the deal's participants.

        Returns:
            A base64-encoded XDR string representing the transaction.
        """
        good_participants = [p for p in self.participants if p.is_done]
        bad_amount = sum((p.amount for p in self.participants if not p.is_done))

        if good_participants:
            participant_reward = (bad_amount / Decimal(2)) / len(good_participants)
            rely_reward = bad_amount - participant_reward * len(good_participants)
        else:
            participant_reward = 0
            rely_reward = bad_amount

        operations = [
            {
                "type": "payment",
                "destination": p.stellar,
                "asset": DEAL_ASSET,
                "amount": str(p.amount + participant_reward),
                "sourceAccount": DEAL_ACCOUNT,
            }
            for p in good_participants
        ]
        if len(good_participants) != len(self.participants):
            operations.append(
                {
                    "type": "payment",
                    "destination": RELY_ACCOUNT,
                    "asset": DEAL_ASSET,
                    "amount": str(rely_reward),
                    "sourceAccount": DEAL_ACCOUNT,
                }
            )
        memo_text = f"Deal #{self.deal_record.id} result"
        return await self._build_envelope(operations, memo_text)

    async def process_any_transaction(
        self, is_result: bool = False
    ) -> TransactionProcessResult:
        """
        Orchestrates loading, validation, and transaction creation for the deal.

        This is the main entry point for processing the business logic of the deal.

        Args:
            is_result: If True, builds a result transaction; otherwise, an initial transaction.

        Returns:
            A TransactionProcessResult containing success status, XDR string, or error messages.
        """
        try:
            await self._load_participants()
        except HolderNotFoundException as e:
            return TransactionProcessResult(success=False, errors=[str(e)])

        validation_errors = self._validate_preconditions()
        if validation_errors:
            return TransactionProcessResult(success=False, errors=validation_errors)

        logger.info(f"Deal {self.deal_record.id} passed precondition validation.")
        try:
            if is_result:
                xdr = await self._build_result_transaction()
            else:
                xdr = await self._build_transaction()
            logger.info(
                f"Built {'result ' if is_result else ''}transaction for deal {self.deal_record.id}: {xdr}"
            )
            return TransactionProcessResult(success=True, xdr=xdr)
        except SdkError as e:
            logger.error(
                f"Stellar SDK error while building {'result ' if is_result else ''}transaction for deal {self.deal_record.id}: {e}"
            )
            return TransactionProcessResult(
                success=False,
                errors=[
                    "❌ Ошибка Stellar SDK при создании транзакции. Пожалуйста, попробуйте позже."
                ],
            )
        except Exception as e:
            logger.error(
                f"Unexpected error building {'result ' if is_result else ''}transaction for deal {self.deal_record.id}: {e}\n{traceback.format_exc()}"
            )
            return TransactionProcessResult(
                success=False, errors=[f"❌ Непредвиденная ошибка: {str(e)}"]
            )


async def _process_deal_transaction(
    deal_record: DealRecord, is_result: bool = False
) -> None:
    """
    Unified handler for processing deal transactions (both initial and result).

    Args:
        deal_record: The deal record to process.
        is_result: If True, processes a result transaction; otherwise, an initial transaction.
    """
    deal_id = deal_record.id
    try:
        lock = _get_deal_lock(deal_id)

        async with lock:
            action_type = "result " if is_result else ""
            logger.info(f"Processing {action_type}deal {deal_id}: {deal_record}")
            deal_aggregate = Deal(deal_record)

            proc_result = await deal_aggregate.process_any_transaction(
                is_result=is_result
            )

            if is_result:
                check_field = "Result_Checked"
                tx_field = "Result_Transaction"
                tx_desc = f"Rely deal result #{deal_id}"
                fail_msg_prefix = "⚠️ Проверка результата сделки"
                fail_msg_suffix = (
                    "Автоматическое создание транзакции результата отменено."
                )
            else:
                check_field = "Checked"
                tx_field = "Transaction"
                tx_desc = f"Rely deal #{deal_id}"
                fail_msg_prefix = "⚠️ Проверка сделки"
                fail_msg_suffix = "Автоматическое создание транзакции отменено."

            if not proc_result.success or not proc_result.xdr:
                errors = proc_result.errors or []
                logger.warning(
                    f"Deal {deal_id} {action_type}failed validation with errors: {errors}"
                )

                # Attempt to uncheck the flag in Grist so user sees it failed there too
                update_success = await deal_repo.update_fields(
                    deal_id, {check_field: False}
                )

                errors_str = "\n".join([f"- {e}" for e in errors])
                text = (
                    f"{fail_msg_prefix} #{deal_id} провалена. Ошибки:\n{errors_str}\n"
                    f"{fail_msg_suffix}"
                )
                if not update_success:
                    text += "\n\n‼️ Не удалось обновить статус в Grist. Проверьте таблицу вручную."

                await TelegramMessenger.send_message(text=text)
                return

            add_success, add_result = await add_transaction(proc_result.xdr, tx_desc)

            if add_success:
                transaction_url = f"https://eurmtl.me/sign_tools/{add_result}"
                logger.info(
                    f"{action_type.capitalize()}transaction for deal {deal_id} added with hash {add_result}. URL: {transaction_url}"
                )
                update_success = await deal_repo.update_fields(
                    deal_id, {tx_field: transaction_url}
                )

                if not is_result:
                    # Specific logic for initial transaction notifications
                    chat_id, message_id = TelegramMessenger.parse_tg_url(
                        deal_record.message_url
                    )
                    mentions = deal_aggregate.mention_string
                    text = f'✅ Пожалуйста, подпишите транзакцию {mentions}\n<a href="{transaction_url}">URL</a>'

                    if not update_success:
                        text += "\n\n‼️ Транзакция создана, но ссылка не сохранена в Grist. Скопируйте её отсюда."

                    if chat_id and message_id:
                        try:
                            await TelegramMessenger.send_message(
                                text=text,
                                chat_id=chat_id,
                                reply_to_message_id=message_id,
                            )
                        except TelegramBadRequest as e:
                            logger.warning(
                                f"Failed to reply to message in chat {chat_id}: {e}"
                            )
                            await TelegramMessenger.send_message(
                                f"{text}\n\n(Не смогли ответить на исходное сообщение: {str(e)})"
                            )
                    else:
                        fallback_text = f'✅ Создана транзакция для сделки #{deal_id}. <a href="{transaction_url}">URL</a>'
                        if not update_success:
                            fallback_text += "\n\n‼️ Ссылка не сохранена в Grist."
                        await TelegramMessenger.send_message(text=fallback_text)
                else:
                    # Specific logic for result transaction notifications
                    text = f'✅ Транзакция результата для сделки #{deal_id} создана.\n<a href="{transaction_url}">URL</a>'
                    if not update_success:
                        text += "\n\n‼️ Ссылка не сохранена в Grist."
                    await TelegramMessenger.send_message(text=text)

            else:
                logger.error(
                    f"Failed to add {action_type}transaction for deal {deal_id}: {add_result}"
                )
                await TelegramMessenger.send_message(
                    text=f"❌ Ошибка добавления транзакции {action_type}для сделки #{deal_id}. Детали: {add_result}"
                )
    except Exception as e:
        logger.error(
            f"Critical error processing deal {deal_id}: {e}\n{traceback.format_exc()}"
        )
        await TelegramMessenger.send_message(
            text=f"‼️ Критическая ошибка при обработке сделки #{deal_id}. Обратитесь к администратору.\nОшибка: {e}"
        )


async def _process_grist_payload(payload: list[dict]) -> None:
    """
    Processes the Grist webhook payload, creating tasks to handle valid deals.

    It iterates through records, identifies deals that need processing,
    and creates background tasks for them.

    Args:
        payload: The JSON payload (list of records) from the Grist webhook.
    """
    try:
        if not isinstance(payload, list):
            msg = f"⚠️ Получен некорректный вебхук от Grist (ожидался список): {str(payload)[:200]}"
            logger.warning(msg)
            await TelegramMessenger.send_message(text=msg)
            return

        for item in payload:
            try:
                record = DealRecord(
                    id=item["id"],
                    checked=item.get("Checked", False),
                    transaction=item.get("Transaction"),
                    message_url=item.get("Message"),
                    result_checked=item.get("Result_Checked", False),
                    result_transaction=item.get("Result_Transaction"),
                )
                if record.checked and not record.transaction:
                    asyncio.create_task(
                        _process_deal_transaction(record, is_result=False)
                    )
                elif record.result_checked and not record.result_transaction:
                    asyncio.create_task(
                        _process_deal_transaction(record, is_result=True)
                    )
            except (KeyError, TypeError) as e:
                logger.warning(
                    f"Could not process record, skipping: {item}. Error: {e}"
                )
                # Optional: notify about specific malformed records if critical,
                # but might be too noisy. Logging is usually enough for data format issues
                # unless it blocks the whole pipeline.

        logger.info(
            f"Grist webhook payload processing initiated for {len(payload)} records."
        )
    except Exception as e:
        logger.error(f"Error processing Grist payload: {e}\n{traceback.format_exc()}")
        await TelegramMessenger.send_message(
            text=f"‼️ Ошибка при обработке вебхука Grist: {e}"
        )


blueprint = Blueprint("rely", __name__)


@blueprint.route("/rely/grist-webhook", methods=["POST", "GET"])
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
