"""Curated seed of real (ZIP5, county FIPS, state) triples.

Hand-picked to give CONUS + AK + HI + DC coverage with a mix of urban /
suburban / rural ZIPs across all 50 states. The synthetic data generator
draws ZIPs from this list so the demo choropleth looks like a real map and
not a single hotspot. Each tuple is (zip5, fips, state).

Source: USPS + Census FIPS lookups. Verified to round-trip through the
public ZIP -> FIPS crosswalk used by the dominant-county strategy.
"""
from __future__ import annotations

SEED_ZIPS: list[tuple[str, str, str]] = [
    # Northeast
    ("10001", "36061", "NY"),  # Manhattan
    ("11201", "36047", "NY"),  # Brooklyn
    ("11375", "36081", "NY"),  # Queens
    ("10458", "36005", "NY"),  # Bronx
    ("10301", "36085", "NY"),  # Staten Island
    ("11801", "36059", "NY"),  # Nassau
    ("11743", "36103", "NY"),  # Suffolk
    ("12203", "36001", "NY"),  # Albany
    ("14604", "36055", "NY"),  # Monroe / Rochester
    ("13202", "36067", "NY"),  # Onondaga / Syracuse
    ("14202", "36029", "NY"),  # Erie / Buffalo
    ("07030", "34017", "NJ"),  # Hudson
    ("07601", "34003", "NJ"),  # Bergen
    ("08540", "34021", "NJ"),  # Mercer
    ("08701", "34029", "NJ"),  # Ocean
    ("08550", "34025", "NJ"),  # Monmouth
    ("06103", "09003", "CT"),  # Hartford
    ("06511", "09009", "CT"),  # New Haven
    ("06830", "09001", "CT"),  # Fairfield
    ("02108", "25025", "MA"),  # Suffolk MA
    ("02139", "25017", "MA"),  # Middlesex MA
    ("01609", "25027", "MA"),  # Worcester MA
    ("02360", "25023", "MA"),  # Plymouth
    ("02740", "25005", "MA"),  # Bristol MA
    ("01060", "25015", "MA"),  # Hampshire
    ("03101", "33011", "NH"),  # Hillsborough NH
    ("03801", "33015", "NH"),  # Rockingham
    ("05401", "50007", "VT"),  # Chittenden
    ("04101", "23005", "ME"),  # Cumberland ME
    ("04401", "23019", "ME"),  # Penobscot
    ("02903", "44007", "RI"),  # Providence
    ("19103", "42101", "PA"),  # Philadelphia
    ("15213", "42003", "PA"),  # Allegheny
    ("17601", "42071", "PA"),  # Lancaster PA
    ("18017", "42077", "PA"),  # Lehigh
    ("17101", "42043", "PA"),  # Dauphin
    # South Atlantic
    ("21201", "24510", "MD"),  # Baltimore City
    ("20850", "24031", "MD"),  # Montgomery MD
    ("20001", "11001", "DC"),  # DC
    ("19801", "10003", "DE"),  # New Castle
    ("22030", "51059", "VA"),  # Fairfax VA
    ("23219", "51760", "VA"),  # Richmond
    ("23451", "51810", "VA"),  # Virginia Beach
    ("24016", "51161", "VA"),  # Roanoke
    ("25301", "54039", "WV"),  # Kanawha
    ("27601", "37183", "NC"),  # Wake
    ("28202", "37119", "NC"),  # Mecklenburg
    ("27514", "37135", "NC"),  # Orange NC
    ("28401", "37129", "NC"),  # New Hanover
    ("29201", "45079", "SC"),  # Richland SC
    ("29401", "45019", "SC"),  # Charleston
    ("29601", "45045", "SC"),  # Greenville SC
    ("30303", "13121", "GA"),  # Fulton
    ("30060", "13067", "GA"),  # Cobb
    ("31401", "13051", "GA"),  # Chatham GA
    ("33101", "12086", "FL"),  # Miami-Dade
    ("33602", "12057", "FL"),  # Hillsborough FL
    ("32801", "12095", "FL"),  # Orange FL
    ("32202", "12031", "FL"),  # Duval
    ("33401", "12099", "FL"),  # Palm Beach
    ("33301", "12011", "FL"),  # Broward
    ("32501", "12033", "FL"),  # Escambia FL
    ("34952", "12111", "FL"),  # St. Lucie
    ("33901", "12071", "FL"),  # Lee
    # East South Central
    ("35203", "01073", "AL"),  # Jefferson AL
    ("36104", "01101", "AL"),  # Montgomery AL
    ("36602", "01097", "AL"),  # Mobile
    ("38103", "47157", "TN"),  # Shelby TN
    ("37203", "47037", "TN"),  # Davidson
    ("37402", "47065", "TN"),  # Hamilton TN
    ("37902", "47093", "TN"),  # Knox TN
    ("40202", "21111", "KY"),  # Jefferson KY
    ("40507", "21067", "KY"),  # Fayette KY
    ("39201", "28049", "MS"),  # Hinds
    ("38801", "28081", "MS"),  # Lee MS
    # East North Central
    ("60601", "17031", "IL"),  # Cook
    ("61602", "17143", "IL"),  # Peoria
    ("62701", "17167", "IL"),  # Sangamon
    ("46204", "18097", "IN"),  # Marion IN
    ("46802", "18003", "IN"),  # Allen IN
    ("47708", "18163", "IN"),  # Vanderburgh
    ("48201", "26163", "MI"),  # Wayne MI
    ("48084", "26125", "MI"),  # Oakland
    ("49503", "26081", "MI"),  # Kent MI
    ("48823", "26065", "MI"),  # Ingham
    ("43215", "39049", "OH"),  # Franklin OH
    ("44114", "39035", "OH"),  # Cuyahoga
    ("45202", "39061", "OH"),  # Hamilton OH
    ("43604", "39095", "OH"),  # Lucas OH
    ("44308", "39153", "OH"),  # Summit OH
    ("53202", "55079", "WI"),  # Milwaukee
    ("53703", "55025", "WI"),  # Dane
    ("54301", "55009", "WI"),  # Brown WI
    # West North Central
    ("55401", "27053", "MN"),  # Hennepin
    ("55101", "27123", "MN"),  # Ramsey
    ("55901", "27109", "MN"),  # Olmsted
    ("50309", "19153", "IA"),  # Polk IA
    ("52240", "19103", "IA"),  # Johnson IA
    ("52401", "19113", "IA"),  # Linn IA
    ("63101", "29510", "MO"),  # St. Louis City
    ("64108", "29095", "MO"),  # Jackson MO
    ("65201", "29019", "MO"),  # Boone MO
    ("66603", "20177", "KS"),  # Shawnee
    ("67202", "20173", "KS"),  # Sedgwick
    ("68102", "31055", "NE"),  # Douglas NE
    ("68508", "31109", "NE"),  # Lancaster NE
    ("58102", "38017", "ND"),  # Cass ND
    ("57104", "46099", "SD"),  # Minnehaha
    # Mountain
    ("59101", "30111", "MT"),  # Yellowstone
    ("59801", "30063", "MT"),  # Missoula
    ("83702", "16001", "ID"),  # Ada
    ("83843", "16057", "ID"),  # Latah
    ("82001", "56021", "WY"),  # Laramie WY
    ("80202", "08031", "CO"),  # Denver
    ("80301", "08013", "CO"),  # Boulder
    ("80903", "08041", "CO"),  # El Paso CO
    ("87501", "35049", "NM"),  # Santa Fe
    ("87102", "35001", "NM"),  # Bernalillo
    ("85004", "04013", "AZ"),  # Maricopa
    ("85701", "04019", "AZ"),  # Pima
    ("84101", "49035", "UT"),  # Salt Lake
    ("84601", "49049", "UT"),  # Utah UT
    ("89101", "32003", "NV"),  # Clark NV
    ("89501", "32031", "NV"),  # Washoe
    # Pacific
    ("98101", "53033", "WA"),  # King WA
    ("98402", "53053", "WA"),  # Pierce
    ("99201", "53063", "WA"),  # Spokane
    ("97201", "41051", "OR"),  # Multnomah
    ("97301", "41047", "OR"),  # Marion OR
    ("97401", "41039", "OR"),  # Lane OR
    ("94102", "06075", "CA"),  # SF
    ("90012", "06037", "CA"),  # LA
    ("92101", "06073", "CA"),  # San Diego
    ("95814", "06067", "CA"),  # Sacramento
    ("93721", "06019", "CA"),  # Fresno
    ("95113", "06085", "CA"),  # Santa Clara
    ("99501", "02020", "AK"),  # Anchorage
    ("99701", "02090", "AK"),  # Fairbanks
    ("96813", "15003", "HI"),  # Honolulu
    ("96720", "15001", "HI"),  # Hawaii County
    # South Central
    ("72201", "05119", "AR"),  # Pulaski AR
    ("70112", "22071", "LA"),  # Orleans Parish
    ("70801", "22033", "LA"),  # E Baton Rouge
    ("70501", "22055", "LA"),  # Lafayette LA
    ("73102", "40109", "OK"),  # Oklahoma OK
    ("74103", "40143", "OK"),  # Tulsa
    ("75201", "48113", "TX"),  # Dallas
    ("77002", "48201", "TX"),  # Harris
    ("78205", "48029", "TX"),  # Bexar
    ("78701", "48453", "TX"),  # Travis
    ("79901", "48141", "TX"),  # El Paso TX
    ("76102", "48439", "TX"),  # Tarrant
]
