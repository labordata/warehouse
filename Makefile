.PHONY: all
all : osha_enforcement.db f7.db nlrb.db opdr.db cats.db voluntary_recognitions.db work_stoppages.db lm20.db chips.db whisard.db nlrb_rc_elections_1961_1998.db lm10.db union_names_crosswalk.db

f7.db : f7.db.zip
	unzip $<
	rm $<
	sqlite-utils enable-fts $@ f7 union_name union_street union_city union_state union_zip
	sqlite-utils query $@ "analyze"
	sqlite-utils query $@ "vacuum"

opdr.db : opdr.db.zip
	unzip $<
	rm $<
	sqlite-utils enable-fts $@ lm_data union_name aff_abbr unit_name desiq_pre desig_num desig_suf street_adr city state zip
	sqlite-utils query $@ "analyze"
	sqlite-utils query $@ "vacuum"

cats.db : nlrb.sqlite.zip
	unzip $<
	rm $<
	mv nlrb.sqlite $@
	sqlite-utils query $@ "analyze"
	sqlite-utils query $@ "vacuum"

%.db : %.db.zip
	unzip $<
	rm $<
	sqlite-utils query $@ "analyze"
	sqlite-utils query $@ "vacuum"

nlrb.db.zip :
	curl -LO https://github.com/labordata/nlrb-data/releases/download/nightly/nlrb.db.zip

f7.db.zip :
	curl -LO http://labordata.github.io/fmcs-f7/f7.db.zip

opdr.db.zip :
	curl -LO https://github.com/labordata/opdr/releases/download/2021-05-31/opdr.db.zip

nlrb.sqlite.zip : 
	curl -LO https://github.com/labordata/nlrb-cats/releases/download/db/nlrb.sqlite.zip

voluntary_recognitions.db :
	curl -LO https://github.com/labordata/nlrb-voluntary-recognitions/raw/main/voluntary_recognitions.db

work_stoppages.db :
	curl -LO https://github.com/labordata/fmcs-work-stoppage/raw/main/work_stoppages.db

lm20.db.zip:
	curl -LO https://github.com/labordata/lm20/releases/download/nightly/lm20.db.zip

chips.db.zip :
	curl -LO https://github.com/labordata/CHIPS/releases/download/current/chips.db.zip

osha_enforcement.db.zip :
	curl -LO https://github.com/labordata/osha-enforcement/releases/download/nightly/osha_enforcement.db.zip

whisard.db.zip :
	curl -LO https://github.com/labordata/whd-compliance/releases/download/nightly/whisard.db.zip

nlrb_rc_elections_1961_1998.db.zip :
	curl -LO https://github.com/labordata/nlrb_old_rcases/raw/master/nlrb_rc_elections_1961_1998.db.zip

lm10.db.zip :
	curl -LO https://github.com/labordata/lm10/releases/download/nightly/lm10.db.zip

union_names_crosswalk.db : union_names_crosswalk.csv
	csvs-to-sqlite $^ $@
	sqlite-utils create-index union_names_crosswalk.db union_names_crosswalk union_name --unique

union_names.csv : f7.db nlrb.db lm20.db voluntary_recognitions.db
	(echo "ATTACH 'f7.db' AS f7; ATTACH 'nlrb.db' AS nlrb; ATTACH 'lm20.db' AS lm20; ATTACH 'voluntary_recognitions.db' AS voluntary_recognitions;"; cat scripts/union_names.sql) | sqlite3 -csv -header :memory: > $@

union_name_crosswalk.csv : union_names.csv
	labor-union-parser $< > $@