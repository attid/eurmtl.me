import re
from datetime import timedelta
from sys import argv
from typing import List, Dict, cast
from sqlalchemy import select, and_, case, distinct, Date, extract, desc, cast as sql_cast
from sqlalchemy.orm import Session
from db.models import *


class EURMTLDictsType:
    Assets = 0
    Accounts = 1


def db_save_dict(session: Session, dict_type: int, dictionary: dict):
    """
    Save a dictionary to the EurmtlDicts table.

    :param session: SQLAlchemy DB session
    :param dict_type: The type of dictionary
    :param dictionary: The dictionary to save
    """
    # Удаляем существующие записи с указанным типом
    session.query(EurmtlDicts).filter(EurmtlDicts.dict_type == dict_type).delete()
    session.commit()

    # Добавляем новые записи
    for key, value in dictionary.items():
        entry = EurmtlDicts(dict_key=key, dict_value=value, dict_type=dict_type)
        session.add(entry)
    session.commit()


def db_get_dict(session: Session, dict_type: int) -> dict:
    """
    Get a dictionary from the EurmtlDicts table.

    :param session:
    :param dict_type: The type of dictionary
    :return: The dictionary
    """
    result = session.query(EurmtlDicts).filter(EurmtlDicts.dict_type == dict_type).all()
    dictionary = {entry.dict_key: entry.dict_value for entry in result}
    return dictionary
