from typing import List, Optional, Tuple, Any
from sqlalchemy import select, desc, exists, func, Text
from sqlalchemy.ext.asyncio import AsyncSession
from db.sql_models import Transactions, Signers, Signatures, Alerts

class TransactionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_hash(self, tx_hash: str) -> Optional[Transactions]:
        result = await self.session.execute(select(Transactions).filter(Transactions.hash == tx_hash))
        return result.scalars().first()

    async def get_by_uuid(self, uuid_val: str) -> Optional[Transactions]:
        result = await self.session.execute(select(Transactions).filter(Transactions.uuid == uuid_val))
        return result.scalars().first()

    async def get_signer_by_public_key(self, public_key: str) -> Optional[Signers]:
        result = await self.session.execute(select(Signers).filter(Signers.public_key == public_key))
        return result.scalars().first()

    async def get_by_sequence(self, sequence: int, exclude_hash: Optional[str] = None) -> List[Transactions]:
        query = select(Transactions).filter(Transactions.stellar_sequence == sequence)
        if exclude_hash:
            query = query.filter(Transactions.hash != exclude_hash)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_pending_for_signer(self, signer: Signers) -> List[Transactions]:
        """
        Get transactions requiring signature from the signer, 
        excluding those already signed by this signer.
        """
        # Original logic:
        # Transactions.json.contains(public_key) AND state == 0
        # Filter out if Signature exists for (hash, signer.id)
        
        # Optimized query using NOT EXISTS
        stmt = select(Transactions).filter(
            Transactions.json.contains(signer.public_key),
            Transactions.state == 0,
            ~exists(select(Signatures.id).filter(
                Signatures.transaction_hash == Transactions.hash,
                Signatures.signer_id == signer.id
            ))
        ).order_by(desc(Transactions.add_dt))
        
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, entity: object) -> None:
        self.session.add(entity)

    async def save(self, transaction: Transactions) -> None:
        """Adds or updates a transaction in the session."""
        await self.session.merge(transaction)
        await self.session.commit()

    async def add_signature(self, signature: Signatures) -> None:
        self.session.add(signature)
        # Commit might be handled by caller if multiple ops
    
    async def add_signer(self, signer: Signers) -> None:
        self.session.add(signer)
        await self.session.commit()

    async def get_signer_by_tg_id(self, tg_id: int) -> Optional[Signers]:
        result = await self.session.execute(select(Signers).filter(Signers.tg_id == tg_id))
        return result.scalars().first()
    
    async def get_signer_by_signature_hint(self, hint: str) -> Optional[Signers]:
        result = await self.session.execute(select(Signers).filter(Signers.signature_hint == hint))
        return result.scalars().first()

    async def get_signature(self, transaction_hash: str, signer_id: int) -> Optional[Signatures]:
        result = await self.session.execute(select(Signatures).filter(
            Signatures.transaction_hash == transaction_hash,
            Signatures.signer_id == signer_id
        ))
        return result.scalars().first()

    async def search_transactions(self, 
                                search_text: str = '', 
                                status: int = -1, 
                                source_account: str = '', 
                                owner_id: Optional[int] = None, 
                                signer_address: str = '',
                                offset: int = 0,
                                limit: int = 100) -> List[Any]:
        
        query = select(
            Transactions.hash.label('hash'),
            Transactions.description.label('description'),
            Transactions.add_dt.label('add_dt'),
            Transactions.state.label('state'),
            Transactions.source_account.label('source_account'),
            func.count(Signatures.signature_xdr).label('signature_count')
        ).outerjoin(
            Signatures, Transactions.hash == Signatures.transaction_hash
        )

        if search_text:
            query = query.filter(Transactions.description.ilike(f'%{search_text}%'))
        if status != -1:
            query = query.filter(Transactions.state == status)
        if source_account:
            query = query.filter(Transactions.source_account == source_account)
        if owner_id is not None:
            query = query.filter(Transactions.owner_id == owner_id)
        if signer_address:
            query = query.join(Signers, Signatures.signer_id == Signers.id).filter(
                Signers.public_key == signer_address)

        query = query.group_by(Transactions).order_by(Transactions.add_dt.desc())
        
        result = await self.session.execute(query.offset(offset).limit(limit))
        return result.all()

    async def get_signature_by_signer_public_key(self, public_key: str, tx_hash: str) -> Optional[Signatures]:
        query = select(Signatures).join(Signers, Signatures.signer_id == Signers.id).filter(
            Signatures.transaction_hash == tx_hash,
            Signers.public_key == public_key,
            Signatures.hidden != 1
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_latest_signature_by_signer(self, public_key: str) -> Optional[Signatures]:
        query = select(Signatures).join(Signers, Signatures.signer_id == Signers.id).filter(
            Signers.public_key == public_key
        ).order_by(Signatures.add_dt.desc())
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_latest_signature_for_source(self, public_key: str, source_account: str) -> Optional[Signatures]:
        query = select(Signatures) \
            .join(Signers, Signatures.signer_id == Signers.id) \
            .join(Transactions, Signatures.transaction_hash == Transactions.hash) \
            .filter(Signers.public_key == public_key,
                    Transactions.source_account == source_account) \
            .order_by(Signatures.add_dt.desc())
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_all_signatures_for_transaction(self, tx_hash: str) -> List[Signatures]:
        query = select(Signatures) \
            .outerjoin(Signers, Signatures.signer_id == Signers.id) \
            .filter(Signatures.transaction_hash == tx_hash).order_by(Signatures.id)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def commit(self):
        await self.session.commit()

