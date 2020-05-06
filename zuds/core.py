import os
import subprocess
import sys
import argparse
import textwrap
from distutils.version import LooseVersion as Version

from skyportal.models import DBSession
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import relationship
from sqlalchemy.exc import UnboundExecutionError
from sqlalchemy.ext.hybrid import hybrid_property

from skyportal import models
from skyportal.model_util import create_tables, drop_tables

from baselayer.app.json_util import to_json

from .file import File
from .secrets import get_secret
from .utils import fid_map
from .status import status
from .env import DependencyError, output

__all__ = ['DBSession', 'create_tables', 'drop_tables',
           'Base', 'init_db', 'join_model', 'ZTFFile',
           'without_database', 'create_database']

Base = models.Base


def run(cmd):
    return subprocess.run(cmd,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          shell=True)


def without_database(retval):
    ## Decorator that tells the wrapped function to return retval if
    ## there is no active database connection
    def wrapped(func):
        def interior(*args, **kwargs):
            try:
                bind = DBSession().get_bind()
            except UnboundExecutionError:
                return retval
            else:
                return func(*args, **kwargs)
        return interior
    return wrapped



def model_representation(o):
    """String representation of sqlalchemy objects."""
    if sa.inspection.inspect(o).expired:
        DBSession().refresh(o)
    inst = sa.inspect(o)
    attr_list = [f"{g.key}={getattr(o, g.key)}"
                 for g in inst.mapper.column_attrs]
    return f"<{type(o).__name__}({', '.join(attr_list)})>"


def model_str(o):
    if sa.inspection.inspect(o).expired:
        DBSession().refresh(o)
    inst = sa.inspect(o)
    attr_list = {g.key: getattr(o, g.key) for g in inst.mapper.column_attrs}
    return to_json(attr_list)


Base.__repr__ = model_representation
Base.__str__ = model_str
Base.modified = sa.Column(
    sa.DateTime(timezone=False),
    server_default=sa.func.now(),
    onupdate=sa.func.now()
)


def join_model(join_table, model_1, model_2, column_1=None, column_2=None,
               fk_1='id', fk_2='id', base=Base):
    """Helper function to create a join table for a many-to-many relationship.
    Parameters
    ----------
    join_table : str
        Name of the new table to be created.
    model_1 : str
        First model in the relationship.
    model_2 : str
        Second model in the relationship.
    column_1 : str, optional
        Name of the join table column corresponding to `model_1`. If `None`,
        then {`table1`[:-1]_id} will be used (e.g., `user_id` for `users`).
    column_2 : str, optional
        Name of the join table column corresponding to `model_2`. If `None`,
        then {`table2`[:-1]_id} will be used (e.g., `user_id` for `users`).
    fk_1 : str, optional
        Name of the column from `model_1` that the foreign key should refer to.
    fk_2 : str, optional
        Name of the column from `model_2` that the foreign key should refer to.
    base : sqlalchemy.ext.declarative.api.DeclarativeMeta
        SQLAlchemy model base to subclass.
    Returns
    -------
    sqlalchemy.ext.declarative.api.DeclarativeMeta
        SQLAlchemy association model class
    """
    table_1 = model_1.__tablename__
    table_2 = model_2.__tablename__
    if column_1 is None:
        column_1 = f'{table_1[:-1]}_id'
    if column_2 is None:
        column_2 = f'{table_2[:-1]}_id'
    reverse_ind_name = f'{join_table}_reverse_ind'

    model_attrs = {
        '__tablename__': join_table,
        'id': None,
        column_1: sa.Column(column_1, sa.ForeignKey(f'{table_1}.{fk_1}',
                                                    ondelete='CASCADE'),
                            primary_key=True),
        column_2: sa.Column(column_2, sa.ForeignKey(f'{table_2}.{fk_2}',
                                                    ondelete='CASCADE'),
                            primary_key=True)
    }

    model_attrs.update({
        model_1.__name__.lower(): relationship(model_1, cascade='all',
                                               foreign_keys=[
                                                   model_attrs[column_1]
                                               ]),
        model_2.__name__.lower(): relationship(model_2, cascade='all',
                                               foreign_keys=[
                                                   model_attrs[column_2]
                                               ]),
        reverse_ind_name: sa.Index(reverse_ind_name,
                                   model_attrs[column_2],
                                   model_attrs[column_1])

    })
    model = type(model_1.__name__ + model_2.__name__, (base,), model_attrs)

    return model


class ZTFFile(Base, File):
    """A database-mapped, disk-mappable memory-representation of a file that
    is associated with a ZTF sky partition. This class is abstract and not
    designed to be instantiated, but it is also not a mixin. Think of it as a
    base class for the polymorphic hierarchy of products in SQLalchemy.

    To create an disk-mappable representation of a fits file that stores data in
    memory and is not mapped to rows in the database, instantiate FITSFile
    directly.
    """

    # this is the discriminator that is used to keep track of different types
    #  of fits files produced by the pipeline for the rest of the hierarchy
    type = sa.Column(sa.Text)

    # all pipeline fits products must implement these four key pieces of
    # metadata. These are all assumed to be not None in valid instances of
    # ZTFFile.

    field = sa.Column(sa.Integer)
    qid = sa.Column(sa.Integer)
    fid = sa.Column(sa.Integer)
    ccdid = sa.Column(sa.Integer)

    copies = relationship('ZTFFileCopy', cascade='all')

    # An index on the four indentifying
    idx = sa.Index('fitsproduct_field_ccdid_qid_fid', field, ccdid, qid, fid)

    __mapper_args__ = {
        'polymorphic_on': type,
        'polymorphic_identity': 'fitsproduct'

    }

    def find_in_dir(self, directory):
        target = os.path.join(directory, self.basename)
        if os.path.exists(target):
            self.map_to_local_file(target)
        else:
            raise FileNotFoundError(
                f'Cannot map "{self.basename}" to "{target}", '
                f'file does not exist.'
            )

    def find_in_dir_of(self, ztffile):
        dirname = os.path.dirname(ztffile.local_path)
        self.find_in_dir(dirname)

    @classmethod
    @without_database(None)
    def get_by_basename(cls, basename):

        obj = DBSession().query(cls).filter(
            cls.basename == basename
        ).first()

        if obj is not None:
            obj.clear()  # get a fresh copy

        if hasattr(obj, 'mask_image'):
            if obj.mask_image is not None:
                obj.mask_image.clear()

        if hasattr(obj, 'catalog'):
            if obj.catalog is not None:
                obj.catalog.clear()

        return obj

    @property
    def relname(self):
        return f'{self.field:06d}/' \
               f'c{self.ccdid:02d}/' \
               f'q{self.qid}/' \
               f'{fid_map[self.fid]}/' \
               f'{self.basename}'

    @hybrid_property
    def relname_hybrid(self):
        return sa.func.format(
            '%s/c%s/q%s/%s/%s',
            sa.func.lpad(sa.func.cast(self.field, sa.Text), 6, '0'),
            sa.func.lpad(sa.func.cast(self.ccdid, sa.Text), 2, '0'),
            self.qid,
            sa.case([
                (self.fid == 1, 'zg'),
                (self.fid == 2, 'zr'),
                (self.fid == 3, 'zi')
            ]),
            self.basename
        )


def check_postgres_extensions(deps, username, password, host, port, database):

    psql_cmd = f'psql '
    flags = f'-U {username} '

    if password:
        psql_cmd = f'PGPASSWORD="{password}" {psql_cmd}'
    flags += f' --no-password'

    if host:
        flags += f' -h {host}'

    if port:
        flags += f' -p {port}'

    get_version = lambda v: v.split('\n')[2].strip()

    fail = []
    for dep, min_version in deps:

        query = f'{dep} >= {min_version}'
        clause = f"SELECT max(extversion) FROM pg_extension WHERE extname = '{dep}';"
        cmd = psql_cmd + f' {flags} {database}'
        splcmd = cmd.split()
        splcmd += ['-c', f"{clause}"]
        cmd += f'-c "{clause}"'

        try:
            with status(query):
                success, out = output(splcmd)
                try:
                    version = get_version(out.decode('utf-8').strip())
                    print(f'[{version.rjust(8)}]'.rjust(40 - len(query)),
                          end='')
                except:
                    raise ValueError('Could not parse version')

                if not (Version(version) >= Version(min_version)):
                    raise RuntimeError(
                        f'Required {min_version}, found {version}'
                    )
        except ValueError:
            print(
                f'\n[!] Sorry, but our script could not parse the output of '
                f'`{" ".join(cmd.replace(password, "***"))}`; '
                f'please file a bug, or see `zuds/core.py`\n'
            )
            raise
        except Exception as e:
            fail.append((dep, e, cmd, min_version))

    if fail:
        failstr = ''
        for (pkg, exc, cmd, min_version) in fail:
            repcmd = cmd
            if password is not None:
                repcmd = repcmd.replace(password, '***')
            failstr += f'    - {pkg}: `{repcmd}`\n'
            failstr += '     ' + str(exc) + '\n'

        msg = f'''
[!] Some system dependencies seem to be unsatisfied

The failed checks were:

{failstr}
'''
        raise DependencyError(msg)



def init_db(timeout=None):

    username = get_secret('db_username')
    password = get_secret('db_password')
    port = get_secret('db_port')
    host = get_secret('db_host')
    dbname = get_secret('db_name')

    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(username, password or '', host or '', port or '', dbname)

    kwargs = {}
    if timeout is not None:
        kwargs['connect_args'] = {"options": f"-c statement_timeout={timeout}"}

    print(f'Checking for postgres extensions:')
    deps = [('q3c', '1.8.0')]
    try:
        check_postgres_extensions(deps, username, password, host, port, dbname)
    except DependencyError:
        DBSession.remove()
        raise

    conn = sa.create_engine(url, client_encoding='utf8', **kwargs)
    DBSession.configure(bind=conn)
    Base.metadata.bind = conn


def create_database(force=False):
    db = get_secret('db_name')
    user = get_secret('db_username')
    host = get_secret('db_host')
    port = get_secret('db_port')
    password = get_secret('db_password')

    psql_cmd = 'psql'
    flags = f'-U {user}'

    if password:
        psql_cmd = f'PGPASSWORD="{password}" {psql_cmd}'
    flags += f' --no-password'

    if host:
        flags += f' -h {host}'

    if port:
        flags += f' -p {port}'

    def test_db(database):
        test_cmd = f"{psql_cmd} {flags} -c 'SELECT 0;' {database}"
        p = run(test_cmd)

        try:
            with status('Testing database connection'):
                if not p.returncode == 0:
                    raise RuntimeError()
        except:
            print(textwrap.dedent(
                f'''
                 !!! Error accessing database:
                 The most common cause of database connection errors is a
                 misconfigured `pg_hba.conf`.
                 We tried to connect to the database with the following parameters:
                   database: {db}
                   username: {user}
                   host:     {host}
                   port:     {port}
                 The postgres client exited with the following error message:
                 {'-' * 78}
                 {p.stderr.decode('utf-8').strip()}
                 {'-' * 78}
                 Please modify your `pg_hba.conf`, and use the following command to
                 check your connection:
                   {test_cmd}
                '''))

            raise


    plat = run('uname').stdout
    if b'Darwin' in plat:
        print('* Configuring MacOS postgres')
        sudo = ''
    else:
        print('* Configuring Linux postgres [may ask for sudo password]')
        sudo = 'sudo -u postgres'

    # Ask for sudo password here so that it is printed on its own line
    # (better than inside a `with status` section)
    run(f'{sudo} echo -n')

    with status(f'Creating user {user}'):
        run(f'{sudo} createuser --superuser {user}')

    if force:
        try:
            with status('Removing existing database'):
                p = run(f'{sudo} dropdb {db}')
                if p.returncode != 0:
                    raise RuntimeError()
        except:
            print('Could not delete database: \n\n'
                  f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n')
            raise

    try:
        with status(f'Creating database'):
            p = run(f'{sudo} createdb {flags} -w {db}')
            msg = f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n'
            if p.returncode != 0 and 'already exists' not in msg:
                raise RuntimeError()

            p = run(f'psql {flags} -c "GRANT ALL PRIVILEGES ON DATABASE {db} TO {user};" {db}')
            msg = f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n'
            if p.returncode != 0:
                raise RuntimeError()

    except:
        print(f'Could not create database: \n\n{msg}\n')
        raise

    try:
        with status(f'Creating extensions'):
            p = run(f'psql {flags} -c "CREATE EXTENSION q3c" {db}')
            msg = f'{textwrap.indent(p.stderr.decode("utf-8").strip(), prefix="  ")}\n'
            if p.returncode != 0 and 'already exists' not in msg:
                raise RuntimeError()
    except:
        print(f'Could not create extensions: \n\n{msg}\n')
        raise

    test_db(db)
