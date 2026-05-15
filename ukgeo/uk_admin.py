"""
Static UK administrative geography reference.
OS Open Names CSV does not include county/unitary authority names as gazetteer
entries, so we maintain this list to supplement the token gazetteer.

To extend: ask an agent to complete any section marked TODO.
Source of truth: ONS Geography Portal / OS Boundary-Line.
"""

# ---------------------------------------------------------------------------
# Metropolitan counties (England)
# ---------------------------------------------------------------------------
METROPOLITAN_COUNTIES = {
    "GREATER MANCHESTER", "MERSEYSIDE", "WEST YORKSHIRE", "SOUTH YORKSHIRE",
    "WEST MIDLANDS", "TYNE AND WEAR",
}

# ---------------------------------------------------------------------------
# Ceremonial / historic counties (England)
# Includes common shortforms people actually use in free text
# ---------------------------------------------------------------------------
CEREMONIAL_COUNTIES = {
    # Yorkshire
    "NORTH YORKSHIRE", "EAST YORKSHIRE", "EAST RIDING OF YORKSHIRE",
    "WEST YORKSHIRE", "SOUTH YORKSHIRE", "YORKSHIRE",
    # Lancashire / NW
    "LANCASHIRE", "CHESHIRE", "CUMBRIA",
    # Midlands
    "WARWICKSHIRE", "WORCESTERSHIRE", "SHROPSHIRE", "STAFFORDSHIRE",
    "DERBYSHIRE", "LEICESTERSHIRE", "NOTTINGHAMSHIRE", "LINCOLNSHIRE",
    "NORTHAMPTONSHIRE", "RUTLAND",
    # East
    "NORFOLK", "SUFFOLK", "ESSEX", "CAMBRIDGESHIRE", "HERTFORDSHIRE",
    "BEDFORDSHIRE", "BUCKINGHAMSHIRE", "OXFORDSHIRE",
    # SE / London
    "KENT", "SURREY", "EAST SUSSEX", "WEST SUSSEX", "HAMPSHIRE",
    "BERKSHIRE", "WILTSHIRE", "DORSET", "SOMERSET",
    # SW
    "DEVON", "CORNWALL", "GLOUCESTERSHIRE",
    # NE
    "DURHAM", "NORTHUMBERLAND", "CLEVELAND",
    # TODO: complete with remaining ceremonial counties
}

# ---------------------------------------------------------------------------
# Unitary authorities (England)
# ---------------------------------------------------------------------------
UNITARY_AUTHORITIES_ENGLAND = {
    "BATH AND NORTH EAST SOMERSET", "BRISTOL", "SOUTH GLOUCESTERSHIRE",
    "NORTH SOMERSET",
    "BRIGHTON AND HOVE", "EAST SUSSEX",
    "MILTON KEYNES", "LUTON", "SOUTHEND-ON-SEA", "THURROCK",
    "MIDDLESBROUGH", "STOCKTON-ON-TEES", "DARLINGTON", "HARTLEPOOL",
    "YORK", "NORTH LINCOLNSHIRE", "NORTH EAST LINCOLNSHIRE",
    "DERBY", "NOTTINGHAM", "LEICESTER",
    "HEREFORDSHIRE", "TELFORD AND WREKIN",
    "STOKE-ON-TRENT",
    "BLACKBURN WITH DARWEN", "BLACKPOOL",
    "HALTON", "WARRINGTON",
    "EAST RIDING OF YORKSHIRE", "KINGSTON UPON HULL",
    "MEDWAY",
    "ISLE OF WIGHT",
    "CORNWALL", "DURHAM", "SHROPSHIRE", "WILTSHIRE",
    "CENTRAL BEDFORDSHIRE", "BEDFORD",
    "CHESHIRE EAST", "CHESHIRE WEST AND CHESTER",
    # TODO: complete with remaining English unitary authorities
}

# ---------------------------------------------------------------------------
# London boroughs
# ---------------------------------------------------------------------------
LONDON_BOROUGHS = {
    "BARKING AND DAGENHAM", "BARNET", "BEXLEY", "BRENT", "BROMLEY",
    "CAMDEN", "CROYDON", "EALING", "ENFIELD", "GREENWICH",
    "HACKNEY", "HAMMERSMITH AND FULHAM", "HARINGEY", "HARROW", "HAVERING",
    "HILLINGDON", "HOUNSLOW", "ISLINGTON", "KENSINGTON AND CHELSEA",
    "KINGSTON UPON THAMES", "LAMBETH", "LEWISHAM", "MERTON", "NEWHAM",
    "REDBRIDGE", "RICHMOND UPON THAMES", "SOUTHWARK", "SUTTON",
    "TOWER HAMLETS", "WALTHAM FOREST", "WANDSWORTH", "WESTMINSTER",
    "CITY OF LONDON",
}

# ---------------------------------------------------------------------------
# Wales — principal areas (unitary authorities since 1996)
# ---------------------------------------------------------------------------
WALES_PRINCIPAL_AREAS = {
    "BLAENAU GWENT", "BRIDGEND", "CAERPHILLY", "CARDIFF", "CARMARTHENSHIRE",
    "CEREDIGION", "CONWY", "DENBIGHSHIRE", "FLINTSHIRE", "GWYNEDD",
    "ISLE OF ANGLESEY", "MERTHYR TYDFIL", "MONMOUTHSHIRE", "NEATH PORT TALBOT",
    "NEWPORT", "PEMBROKESHIRE", "POWYS", "RHONDDA CYNON TAF", "SWANSEA",
    "TORFAEN", "VALE OF GLAMORGAN", "WREXHAM",
}

# ---------------------------------------------------------------------------
# Scotland — council areas
# ---------------------------------------------------------------------------
SCOTLAND_COUNCIL_AREAS = {
    "ABERDEEN CITY", "ABERDEENSHIRE", "ANGUS", "ARGYLL AND BUTE",
    "CLACKMANNANSHIRE", "DUMFRIES AND GALLOWAY", "DUNDEE CITY",
    "EAST AYRSHIRE", "EAST DUNBARTONSHIRE", "EAST LOTHIAN", "EAST RENFREWSHIRE",
    "EDINBURGH", "CITY OF EDINBURGH", "EILEAN SIAR", "FALKIRK", "FIFE",
    "GLASGOW CITY", "HIGHLAND", "INVERCLYDE", "MIDLOTHIAN", "MORAY",
    "NORTH AYRSHIRE", "NORTH LANARKSHIRE", "ORKNEY ISLANDS",
    "PERTH AND KINROSS", "RENFREWSHIRE", "SCOTTISH BORDERS",
    "SHETLAND ISLANDS", "SOUTH AYRSHIRE", "SOUTH LANARKSHIRE", "STIRLING",
    "WEST DUNBARTONSHIRE", "WEST LOTHIAN",
}

# ---------------------------------------------------------------------------
# Northern Ireland — districts
# ---------------------------------------------------------------------------
NORTHERN_IRELAND_DISTRICTS = {
    "ANTRIM AND NEWTOWNABBEY", "ARDS AND NORTH DOWN", "ARMAGH CITY BANBRIDGE AND CRAIGAVON",
    "BELFAST", "CAUSEWAY COAST AND GLENS", "DERRY CITY AND STRABANE",
    "FERMANAGH AND OMAGH", "LISBURN AND CASTLEREAGH", "MID AND EAST ANTRIM",
    "MID ULSTER", "NEWRY MOURNE AND DOWN",
}

# ---------------------------------------------------------------------------
# Common shortforms / aliases people use in free text
# Maps alias → canonical (canonical should appear in one of the sets above)
# ---------------------------------------------------------------------------
ADMIN_ALIASES = {
    "YORKS": "YORKSHIRE",
    "W YORKS": "WEST YORKSHIRE",
    "S YORKS": "SOUTH YORKSHIRE",
    "N YORKS": "NORTH YORKSHIRE",
    "E YORKS": "EAST YORKSHIRE",
    "LANCS": "LANCASHIRE",
    "LINCS": "LINCOLNSHIRE",
    "NOTTS": "NOTTINGHAMSHIRE",
    "LEICS": "LEICESTERSHIRE",
    "NORTHANTS": "NORTHAMPTONSHIRE",
    "HERTS": "HERTFORDSHIRE",
    "BEDS": "BEDFORDSHIRE",
    "BUCKS": "BUCKINGHAMSHIRE",
    "OXON": "OXFORDSHIRE",
    "HANTS": "HAMPSHIRE",
    "WILTS": "WILTSHIRE",
    "GLOS": "GLOUCESTERSHIRE",
    "SHROPS": "SHROPSHIRE",
    "STAFFS": "STAFFORDSHIRE",
    "DERBYS": "DERBYSHIRE",
    "WARKS": "WARWICKSHIRE",
    "WORCS": "WORCESTERSHIRE",
    "CAMBS": "CAMBRIDGESHIRE",
    "NORTHUMB": "NORTHUMBERLAND",
    "CO DURHAM": "DURHAM",
    # Scotland
    "EDINBURGH": "CITY OF EDINBURGH",
    "GLASGOW": "GLASGOW CITY",
}

# ---------------------------------------------------------------------------
# Combined set for gazetteer — everything that should tag as "county"
# ---------------------------------------------------------------------------
ALL_ADMIN = (
    METROPOLITAN_COUNTIES
    | CEREMONIAL_COUNTIES
    | UNITARY_AUTHORITIES_ENGLAND
    | LONDON_BOROUGHS
    | WALES_PRINCIPAL_AREAS
    | SCOTLAND_COUNCIL_AREAS
    | NORTHERN_IRELAND_DISTRICTS
    | set(ADMIN_ALIASES.keys())
)


def resolve_alias(name: str) -> str:
    """Resolve a shortform alias to its canonical name."""
    return ADMIN_ALIASES.get(name.upper(), name.upper())