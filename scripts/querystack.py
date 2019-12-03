import db
from datetime import timedelta
import pandas as pd
import sys

outfile = sys.argv[1]

db.init_db()

# set the stack window size
STACK_WINDOW = 7.  # days
STACK_INTERVAL = timedelta(days=STACK_WINDOW)

# create the date table
gs = db.sa.func.generate_series
timetype = db.sa.DateTime(timezone=False)
mindate = db.sa.cast('2017-01-01', timetype)
maxdate = db.sa.cast(db.sa.func.now(), timetype)

lcol = gs(mindate,
          maxdate - STACK_INTERVAL,
          STACK_INTERVAL).label('left')

rcol = gs(mindate + STACK_INTERVAL,
          maxdate,
          STACK_INTERVAL).label('right')

daterange = db.DBSession().query(lcol, rcol).subquery()

target = db.sa.func.array_agg(db.SingleEpochSubtraction.id).label('target')
stacksize = db.sa.func.array_length(target, 1).label('stacksize')
stackcond = stacksize >= 3
jcond = db.sa.and_(db.ScienceImage.obsdate > daterange.c.left,
                   db.ScienceImage.obsdate <= daterange.c.right)

res = db.DBSession().query(db.SingleEpochSubtraction.field,
                           db.SingleEpochSubtraction.ccdid,
                           db.SingleEpochSubtraction.qid,
                           db.SingleEpochSubtraction.fid,
                           daterange.c.left, daterange.c.right,
                           target).select_from(
    db.sa.join(db.SingleEpochSubtraction, db.ScienceImage.__table__,
               db.SingleEpochSubtraction.target_image_id ==
               db.ScienceImage.id).innerjoin(daterange, jcond)
).group_by(
    db.SingleEpochSubtraction.field,
    db.SingleEpochSubtraction.ccdid,
    db.SingleEpochSubtraction.qid,
    db.SingleEpochSubtraction.fid,
    daterange.c.left, daterange.c.right
).having(
    stackcond
).order_by(
    stacksize.desc()
).subquery()

excludecond = db.sa.and_(
    db.ScienceCoadd.field == res.c.field,
    db.ScienceCoadd.ccdid == res.c.ccdid,
    db.ScienceCoadd.qid == res.c.qid,
    db.ScienceCoadd.fid == res.c.fid,
    db.ScienceCoadd.binleft == res.c.left,
    db.ScienceCoadd.binright == res.c.right
)

final = db.DBSession().query(res).outerjoin(
    db.ScienceCoadd, excludecond
)

result = pd.read_sql(final.statement, db.DBSession().get_bind())

with open(outfile, 'w') as f:
    for _, row in result.iterrows():
        f.write(f'{",".join(row["target"])}\n')
