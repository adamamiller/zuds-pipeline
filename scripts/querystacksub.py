import db
from datetime import timedelta
import pandas as pd
import sys

# this spits out a list of all the stacks that dont have corresponding
# StackedSubtractions


outfile = sys.argv[1]

final = db.DBSession().query(db.ScienceCoadd).outerjoin(
    db.StackedSubtraction
).filter(db.StackedSubtraction.id == None)

result = pd.read_sql(final.statement, db.DBSession().get_bind())
result.to_csv(outfile, index=False)
