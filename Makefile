.PHONY: all
all : f7.db nlrb.db opdr.db cats.db voluntary_recognitions.db work_stoppages.db lm20.db chips.db osha_enforcement.db whisard.db crosswalk.db nlrb_rc_elections_1961_1998.db

f7.db : f7.db.zip
	unzip $<
	sqlite-utils enable-fts $@ f7 union_name union_street union_city union_state union_zip
	echo "analyze; vacuum;" | sqlite3 $@

opdr.db : opdr.db.zip
	unzip $<
	sqlite-utils enable-fts $@ lm_data union_name aff_abbr unit_name desiq_pre desig_num desig_suf street_adr city state zip
	echo "analyze; vacuum;" | sqlite3 $@

cats.db : nlrb.sqlite.zip
	unzip $<
	mv nlrb.sqlite $@
	echo "analyze; vacuum;" | sqlite3 $@

%.db : %.db.zip
	unzip $<
	echo "analyze; vacuum;" | sqlite3 $@

nlrb.db.zip :
	wget https://github.com/labordata/nlrb-data/releases/download/nightly/nlrb.db.zip

f7.db.zip :
	wget http://labordata.github.io/fmcs-f7/f7.db.zip

opdr.db.zip :
	wget https://github.com/labordata/opdr/releases/download/2021-05-31/opdr.db.zip

nlrb.sqlite.zip : 
	wget https://github.com/labordata/nlrb-cats/releases/download/db/nlrb.sqlite.zip

voluntary_recognitions.db :
	wget https://github.com/labordata/nlrb-voluntary-recognitions/raw/main/voluntary_recognitions.db

work_stoppages.db :
	wget https://github.com/labordata/fmcs-work-stoppage/raw/main/work_stoppages.db

lm20.db.zip:
	wget https://github.com/labordata/lm20/releases/download/nightly/lm20.db.zip

chips.db.zip :
	wget https://github.com/labordata/CHIPS/releases/download/current/chips.db.zip

osha_enforcement.db.zip :
	wget https://github.com/labordata/osha-enforcement/releases/download/nightly/osha_enforcement.db.zip

whisard.db.zip :
	wget https://github.com/labordata/whd-compliance/releases/download/nightly/whisard.db.zip

nlrb_rc_elections_1961_1998.db.zip :
	wget https://github.com/labordata/nlrb_old_rcases/raw/master/nlrb_rc_elections_1961_1998.db.zip

crosswalk.db : whd_establishment.csv osha_establishment.csv
	csvs-to-sqlite $^ $@

whd_to_match.csv : whisard.db
	sqlite3 $< -csv -header < scripts/whd_to_match.sql > $@

osha_to_match.csv : osha_enforcement.db
	sqlite3 $< -csv -header < scripts/osha_to_match.sql > $@

whd_establishment.csv : whd_to_match.csv
	employerlookup $< --identifier=case_id > $@

osha_establishment.csv : osha_to_match.csv
	employerlookup $< --identifier=activity_nr > $@
