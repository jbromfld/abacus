"""Run one local Abacus server after PostgreSQL/schema and port are ready."""
import argparse
import logging
from pathlib import Path
import socket
import time

ROOT = Path(__file__).resolve().parents[1]


def port_number(value):
    number = int(value)
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError('Port must be between 1 and 65535.')
    return number


def port_available(port):
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        # Match Uvicorn's reuse behavior: a recently stopped server can leave
        # TIME_WAIT sockets even though no listener remains.
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:
            probe.bind(('127.0.0.1',port))
            return True
        except OSError:
            return False


def database_problem(root):
    from sqlalchemy import create_engine,text
    from sqlalchemy.exc import SQLAlchemyError
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from abacus.config import database_url
    engine = None
    try:
        engine=create_engine(database_url(),connect_args={'connect_timeout':5})
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            applied=set(MigrationContext.configure(connection).get_current_heads())
        expected=set(ScriptDirectory(str(root/'migrations')).get_heads())
        if applied != expected:
            return 'Database migrations are pending. Run uv run alembic upgrade head in the workspace.'
    except SQLAlchemyError:
        # Connection errors can contain configuration details. Never log credentials/URLs.
        return 'Waiting for PostgreSQL. Check that it is running and .env credentials are valid.'
    finally:
        if engine is not None:engine.dispose()
    return None


def readiness_problem(root,port):
    if not (root/'frontend/dist/index.html').is_file():
        return 'Frontend build missing. Run npm run build --prefix frontend in the workspace.'
    if not port_available(port):
        return f'Port {port} is already in use; waiting rather than starting a second server.'
    return database_problem(root)


def wait_until_ready(check,delay=5):
    previous=None
    while True:
        problem=check()
        if problem is None:return
        if problem!=previous:
            logging.warning(problem)
            previous=problem
        time.sleep(delay)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=port_number,default=8017)
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('alembic').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    wait_until_ready(lambda:readiness_problem(ROOT,args.port))
    logging.info('Starting Abacus at http://127.0.0.1:%s (one worker).',args.port)
    import uvicorn
    uvicorn.run('abacus.main:app',host='127.0.0.1',port=args.port,workers=1,access_log=False)


if __name__=='__main__':
    main()
