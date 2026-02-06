import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from random import shuffle

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from quart import Markup

from stellar_sdk import DecoratedSignature, Keypair, Network, TransactionEnvelope
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
from stellar_sdk.sep import stellar_uri

from db.sql_models import Transactions, Signers, Signatures, Alerts
from infrastructure.repositories.transaction_repository import TransactionRepository
from other.grist_tools import load_users_from_grist
from other.config_reader import config
from other.telegram_tools import skynet_bot
from other.cache_tools import async_cache_with_ttl
from services.stellar_client import check_user_in_sign, update_transaction_sources, check_publish_state

logger = logging.getLogger(__name__)

class TransactionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TransactionRepository(session)

    async def get_transaction_by_hash(self, tr_hash: str) -> Optional[Transactions]:
        if len(tr_hash) == 64:
            return await self.repo.get_by_hash(tr_hash)
        else:
            return await self.repo.get_by_uuid(tr_hash)

    async def get_transaction_details(self, tr_hash: str, user_id: int) -> Dict[str, Any]:
        """
        Prepares all data needed for the transaction details pages.
        """
        transaction = await self.get_transaction_by_hash(tr_hash)
        if transaction is None:
            return None

        # Check privileges (moved from router)
        # Assuming admin_weight logic is simple enough to keep here or move to a helper
        in_sign = await check_user_in_sign(tr_hash)
        admin_weight = 2 if in_sign else 0

        # Alert status
        alert = False
        if user_id > 0:
            result = await self.session.execute(
                select(Alerts).filter(Alerts.transaction_hash == tr_hash, Alerts.tg_id == user_id)
            )
            alert = result.scalars().first()

        try:
            json_transaction = json.loads(transaction.json)
        except Exception:
            # Handle bad JSON
            return {
                "error": "BAD xdr. Can`t load",
                "transaction": transaction
            }

        transaction_env = TransactionEnvelope.from_xdr(
            transaction.body,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )

        # Preload users
        all_public_keys = [signer[0] for address in json_transaction for signer in json_transaction[address]['signers']]
        user_map = await load_users_from_grist(all_public_keys)

        signers_table = []
        bad_signers = []
        signatures_list = [] # For display
        current_tg_id = user_id if user_id and user_id > 0 else None

        # Process signers and thresholds
        for address in json_transaction:
            signers = []
            has_votes = 0
            
            sorted_signers = sorted(json_transaction[address]['signers'], key=lambda x: x[1])
            
            for signer in sorted_signers:
                public_key = signer[0]
                weight = signer[1]
                
                signature = await self.repo.get_signature_by_signer_public_key(public_key, transaction.hash)
                db_signer = await self.repo.get_signer_by_public_key(public_key)
                
                signature_dt = await self.repo.get_latest_signature_by_signer(public_key)
                signature_source_dt = await self.repo.get_latest_signature_for_source(public_key, address)

                user = user_map.get(public_key)
                username = user.username if user else None
                user_tg_id = user.telegram_id if user else None
                if user_tg_id is None and db_signer and db_signer.tg_id:
                    user_tg_id = db_signer.tg_id
                is_current_user = bool(
                    current_tg_id is not None
                    and user_tg_id is not None
                    and int(user_tg_id) == int(current_tg_id)
                )

                signature_days_any = (datetime.now() - signature_dt.add_dt).days if signature_dt else None
                signature_days_source = (datetime.now() - signature_source_dt.add_dt).days if signature_source_dt else None

                if signature:
                    if has_votes < int(json_transaction[address]['threshold']) or int(json_transaction[address]['threshold']) == 0:
                         signature_xdr = DecoratedSignature.from_xdr_object(
                             DecoratedSignatureXdr.from_xdr(signature.signature_xdr)
                         )
                         if signature_xdr not in transaction_env.signatures:
                             transaction_env.signatures.append(signature_xdr)
                    has_votes += weight
                else:
                    bad_signers.append(username)
                
                if weight > 0:
                    signers.append([
                        public_key,
                        username,
                        {
                            "source": signature_days_source,
                            "any": signature_days_any
                        },
                        weight,
                        signature,
                        is_current_user
                    ])
            
            signers.sort(key=lambda k: k[3], reverse=True)
            signers_table.append({
                "threshold": json_transaction[address]['threshold'],
                "sources": address,
                "has_votes": has_votes,
                "signers": signers
            })

        # Process signatures for display list
        db_signatures = await self.repo.get_all_signatures_for_transaction(transaction.hash)
        
        # Optimized loading for signature users
        signer_ids = [s.signer_id for s in db_signatures if s.signer_id]
        if signer_ids:
             result = await self.session.execute(select(Signers).filter(Signers.id.in_(signer_ids)))
             all_signers = result.scalars().all()
        else:
             all_signers = []
        signer_map = {s.id: s for s in all_signers}
        
        sig_public_keys = [s.public_key for s in all_signers]
        sig_user_map = await load_users_from_grist(sig_public_keys)

        for signature in db_signatures:
            signer_instance = signer_map.get(signature.signer_id)
            username = None
            if signer_instance:
                user = sig_user_map.get(signer_instance.public_key)
                if user:
                    username = user.username
            
            signatures_list.append([signature.id, signature.add_dt, username, signature.signature_xdr, signature.hidden])

        publish_state = await check_publish_state(transaction.hash)

        return {
            "transaction": transaction,
            "tx_description": transaction.description,
            "tx_body": transaction.body,
            "tx_hash": transaction.hash,
            "uuid": transaction.uuid,
            "user_id": user_id,
            "bad_signers": set(bad_signers),
            "signatures": signatures_list,
            "signers_table": signers_table,
            "alert": alert,
            "tx_full": transaction_env.to_xdr(), # With added signatures
            "admin_weight": admin_weight,
            "publish_state": publish_state,
            "transaction_env": transaction_env # Returning object in case we need to modify it further
        }

    async def update_signature_visibility(self, signature_id: int, hide: bool):
        result = await self.session.execute(select(Signatures).filter(Signatures.id == signature_id))
        signature_to_update = result.scalars().first()
        if signature_to_update:
            signature_to_update.hidden = 1 if hide else 0
            await self.session.commit()
            return True
        return False

    async def sign_transaction_from_xdr(self, tx_body_xdr: str) -> Dict[str, Any]:
        """
        Parses XDR, extracts signatures, verifies them, and saves to DB.
        Corresponds to `parse_xdr_for_signatures`
        """
        result = {"SUCCESS": False, "MESSAGES": []}
        
        try:
            tr_full = TransactionEnvelope.from_xdr(
                tx_body_xdr, 
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
            )
            result["hash"] = tr_full.hash_hex()
        except Exception:
            result['MESSAGES'].append('BAD xdr. Can`t load')
            return result

        transaction = await self.repo.get_by_hash(tr_full.hash_hex())
        if transaction is None:
            result['MESSAGES'].append('Transaction not found')
            return result

        try:
            json_transaction = json.loads(transaction.json)
        except Exception:
            result['MESSAGES'].append('Can`t load json')
            return result

        if len(tr_full.signatures) > 0:
            all_signer_hints = [s.signature_hint.hex() for s in tr_full.signatures]
            
            # Preload signers by hint
            db_signers_res = await self.session.execute(
                select(Signers).filter(Signers.signature_hint.in_(all_signer_hints))
            )
            all_db_signers = db_signers_res.scalars().all()
            
            signer_map = {s.signature_hint: s for s in all_db_signers}
            user_map = await load_users_from_grist([s.public_key for s in all_db_signers])

            for signature in tr_full.signatures:
                db_signer = signer_map.get(signature.signature_hint.hex())
                user = user_map.get(db_signer.public_key) if db_signer else None
                username = user.username if user else None

                # Check if already exists
                existing_sig_res = await self.session.execute(
                    select(Signatures).filter(
                        Signatures.transaction_hash == transaction.hash,
                        Signatures.signature_xdr == signature.to_xdr_object().to_xdr()
                    )
                )
                if existing_sig_res.scalars().first():
                    result['MESSAGES'].append(f'Can`t add {username if db_signer else None}. Already was added.')
                else:
                    # Validate signer is in transaction requirements
                    all_sign = []
                    for record in json_transaction:
                         all_sign.extend(json_transaction[record]['signers'])
                    
                    # Find signer public key matching hint
                    json_signer = list(filter(lambda x: x[2] == signature.signature_hint.hex(), all_sign))
                    
                    if len(json_signer) == 0:
                        result['MESSAGES'].append(f'Bad signature. {signature.signature_hint.hex()} not found')
                    else:
                        user_keypair = Keypair.from_public_key(json_signer[0][0])
                        try:
                            user_keypair.verify(data=tr_full.hash(), signature=signature.signature)
                            
                            new_sig = Signatures(
                                signature_xdr=signature.to_xdr_object().to_xdr(),
                                signer_id=db_signer.id if db_signer else None,
                                transaction_hash=transaction.hash
                            )
                            self.session.add(new_sig)
                            
                            text = f'Added signature from {username}'
                            result['MESSAGES'].append(text)
                            result['SUCCESS'] = True
                            
                            await self.alert_signers_notify(
                                tr_hash=transaction.hash, 
                                small_text=text,
                                tx_description=transaction.description
                            )
                        except BadSignatureError:
                             result['MESSAGES'].append(f'Bad signature. {signature.signature_hint.hex()} not verify')
            
            await self.session.commit()
            
        return result

    async def alert_signers_notify(self, tr_hash: str, small_text: str, tx_description: str):
        text = (f'Transaction <a href="https://eurmtl.me/sign_tools/{tr_hash}">{tx_description}</a> : '
                f'{small_text}.')
        result = await self.session.execute(select(Alerts).filter(Alerts.transaction_hash == tr_hash))
        alert_query = result.scalars().all()
        for alert in alert_query:
            try:
                await skynet_bot.send_message(chat_id=alert.tg_id, text=text, disable_web_page_preview=True, parse_mode='HTML')
            except Exception as e:
                logger.error(f"Failed to send alert to {alert.tg_id}: {e}")

    async def search_transactions(self, filters: Dict[str, Any], limit: int, offset: int) -> List[Any]:
        return await self.repo.search_transactions(
            search_text=filters.get('text', ''),
            status=filters.get('status', -1),
            source_account=filters.get('source_account', ''),
            owner_id=filters.get('owner_id'),
            signer_address=filters.get('signer_address', ''),
            offset=offset,
            limit=limit
        )
    
    @async_cache_with_ttl(ttl_seconds=7*24*60*60, maxsize=30)  # Кеш на неделю с лимитом 30 транзакций
    async def create_transaction_uri(self, tr_hash: str) -> Optional[str]:
        transaction = await self.get_transaction_by_hash(tr_hash)
        if not transaction:
            return None
            
        transaction_envelope = TransactionEnvelope.from_xdr(transaction.body, Network.PUBLIC_NETWORK_PASSPHRASE)
        msg = transaction.description[:300] if transaction.description else None
        
        transaction_uri = stellar_uri.TransactionStellarUri(
            transaction_envelope=transaction_envelope,
            callback="https://eurmtl.me/remote/sep07",
            origin_domain="eurmtl.me",
            message=msg
        )
        transaction_uri.sign(config.domain_key.get_secret_value())
        return transaction_uri.to_uri()
    
    async def refresh_transaction(self, tr_hash: str, user_id: int) -> Tuple[bool, str]:
        transaction = await self.get_transaction_by_hash(tr_hash)
        if not transaction:
             return False, 'Transaction not exist'
             
        in_sign = await check_user_in_sign(tr_hash)
        admin_weight = 2 if in_sign else 0
        is_owner = transaction.owner_id and int(transaction.owner_id) == int(user_id) if user_id else False

        if admin_weight > 0 or is_owner:
            success = await update_transaction_sources(transaction)
            if success:
                return True, 'Информация о подписантах и порогах успешно обновлена!'
            else:
                 return False, 'Не удалось обновить информацию о подписантах.'
        else:
             return False, 'У вас нет прав для выполнения этого действия.'

    async def add_or_remove_alert(self, tr_hash: str, tg_id: int) -> Dict[str, Any]:
         try:
            result = await self.session.execute(select(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                    Alerts.tg_id == tg_id))
            alert = result.scalars().first()
            if alert is None:
                alert = Alerts(tg_id=tg_id, transaction_hash=tr_hash)
                self.session.add(alert)
                await self.session.commit()
                return {
                    'success': True,
                    'icon': 'ti-bell-ringing',
                    'message': 'Alert added successfully'
                }
            else:
                await self.session.delete(alert)
                await self.session.commit()
                return {
                    'success': True,
                    'icon': 'ti-bell-off',
                    'message': 'Alert removed successfully'
                }
         except Exception as e:
            return {
                'success': False,
                'message': f'An error occurred: {str(e)}'
            }

    async def get_pending_transactions_for_signer(self, public_key: str) -> List[Dict[str, Any]]:
        signer = await self.repo.get_signer_by_public_key(public_key)
        if not signer:
            return []
            
        transactions = await self.repo.get_pending_for_signer(signer)
        
        result_list = []
        for transaction in transactions:
            result_list.append({
                'hash': transaction.hash,
                'body': transaction.body,
                'add_dt': transaction.add_dt.isoformat(),
                'description': transaction.description
            })
        return result_list
