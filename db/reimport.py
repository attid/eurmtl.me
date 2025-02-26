# import asyncio
# from concurrent.futures import ThreadPoolExecutor
#
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
#
# from other.config_reader import config
# from db import mongo
# from db.sql_models import Signers
#
# # Предположим, что у вас есть модель Signers
# # from your_models_module import Signers
#
# # Настройка подключения к базе данных
# engine = create_engine(config.db_dsn, pool_pre_ping=True)
# Session = sessionmaker(bind=engine)
#
#
# async def get_all_users(db_session):
#     # Используем run_in_executor для выполнения синхронного запроса в асинхронном контексте
#     loop = asyncio.get_running_loop()
#     with ThreadPoolExecutor() as pool:
#         users = await loop.run_in_executor(pool, lambda: db_session.query(Signers).all())
#     return users
#
#
# async def main():
#     db_session = Session()
#     users = await get_all_users(db_session)
#     for user in users:
#         if user.username != 'FaceLess':
#             mongo_user = await mongo.User.find_by_stellar_id(user.public_key)
#             mongo_user_username = mongo_user.username if mongo_user else None
#             if mongo_user_username:
#                 if user.username.lower() != '@' + mongo_user_username.lower():
#                     #print(user.username, user.tg_id, user.public_key, mongo_user_username)
#                     pass
#             else:
#                 # **** выше менять запрещено
#                 # print(user.username, user.tg_id, user.public_key, mongo_user_username)
#
#                 # Проверяем, существует ли уже пользователь с таким `tg_id`
#                 mongo_user = await mongo.engine.find_one(mongo.User, mongo.User.username == user.username[1:])
#                 if mongo_user:
#                     # Если пользователь найден, добавляем `public_key` в список `stellar`, если его там нет
#                     if user.public_key not in mongo_user.stellar:
#                         mongo_user.stellar.append(user.public_key)
#                         print('updated ', mongo_user, mongo_user.stellar)
#                         await mongo.engine.save(mongo_user)
#                 else:
#                     # Если пользователь не найден, создаем нового
#
#                     # new_user = mongo.User(
#                     #     telegram_id=int(user.tg_id),
#                     #     username=user.username[1:],
#                     #     stellar=[user.public_key]  # создаем новый список с `public_key`
#                     # )
#                     print('no found ', user.username, user.tg_id, user.public_key, mongo_user_username)
#                     # await mongo.engine.save(new_user)
#
#     db_session.close()
#
# async def main2():
#     public_key = 'GCKWH4EEYSLJMGA5DOJYQFOBUV57PLJYXBA7I42ZERZEMRSVDT6WLEDS'
#     mongo_user = await mongo.User.find_by_stellar_id(public_key)
#     print(mongo_user)
#
#
# if __name__ == "__main__":
#     asyncio.run(main2())
