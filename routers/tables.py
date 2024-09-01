from quart import Blueprint

blueprint = Blueprint('tables', __name__)


@blueprint.route('/tables', methods=('GET', 'POST'))
async def cmd_tables():
    pass
