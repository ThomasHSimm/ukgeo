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


# ---------------------------------------------------------------------------
# Approximate BNG extents for admin-context spatial filtering.
#
# Values are (xmin, ymin, xmax, ymax) in EPSG:27700 British National Grid metres.
# Tighter entries cover the common ambiguous free-text cases; broader country/
# region fallbacks keep every ALL_ADMIN token usable without overfitting to one
# OS Boundary-Line release.
# ---------------------------------------------------------------------------
ENGLAND_BNG_EXTENT = (0.0, 0.0, 660000.0, 660000.0)
WALES_BNG_EXTENT = (150000.0, 150000.0, 360000.0, 400000.0)
SCOTLAND_BNG_EXTENT = (50000.0, 530000.0, 470000.0, 1220000.0)
NORTHERN_IRELAND_BNG_EXTENT = (-100000.0, 500000.0, 200000.0, 900000.0)

ADMIN_BNG_EXTENTS = {
    **{name: ENGLAND_BNG_EXTENT for name in (
        METROPOLITAN_COUNTIES
        | CEREMONIAL_COUNTIES
        | UNITARY_AUTHORITIES_ENGLAND
        | LONDON_BOROUGHS
    )},
    **{name: WALES_BNG_EXTENT for name in WALES_PRINCIPAL_AREAS},
    **{name: SCOTLAND_BNG_EXTENT for name in SCOTLAND_COUNCIL_AREAS},
    **{name: NORTHERN_IRELAND_BNG_EXTENT for name in NORTHERN_IRELAND_DISTRICTS},
}

ADMIN_BNG_EXTENTS.update({
    # England: counties and metropolitan/unitary areas.
    "BEDFORDSHIRE": (500000.0, 218000.0, 528000.0, 268000.0),
    "BERKSHIRE": (440000.0, 160000.0, 500000.0, 190000.0),
    "BRISTOL": (350000.0, 170000.0, 365000.0, 185000.0),
    "BUCKINGHAMSHIRE": (450000.0, 175000.0, 510000.0, 260000.0),
    "CAMBRIDGESHIRE": (500000.0, 240000.0, 560000.0, 310000.0),
    "CHESHIRE": (330000.0, 340000.0, 395000.0, 405000.0),
    "CORNWALL": (140000.0, 0.0, 285000.0, 105000.0),
    "CUMBRIA": (285000.0, 470000.0, 390000.0, 590000.0),
    "DERBYSHIRE": (410000.0, 320000.0, 450000.0, 405000.0),
    "DEVON": (210000.0, 50000.0, 330000.0, 160000.0),
    "DORSET": (340000.0, 70000.0, 410000.0, 125000.0),
    "DURHAM": (390000.0, 500000.0, 435000.0, 550000.0),
    "EAST RIDING OF YORKSHIRE": (455000.0, 425000.0, 545000.0, 470000.0),
    "EAST SUSSEX": (500000.0, 90000.0, 565000.0, 120000.0),
    "EAST YORKSHIRE": (455000.0, 425000.0, 545000.0, 470000.0),
    "ESSEX": (520000.0, 170000.0, 620000.0, 235000.0),
    "GLOUCESTERSHIRE": (350000.0, 185000.0, 410000.0, 255000.0),
    "GREATER MANCHESTER": (360000.0, 385000.0, 405000.0, 425000.0),
    "HAMPSHIRE": (420000.0, 90000.0, 490000.0, 160000.0),
    "HEREFORDSHIRE": (320000.0, 220000.0, 370000.0, 270000.0),
    "HERTFORDSHIRE": (500000.0, 185000.0, 540000.0, 225000.0),
    "ISLE OF WIGHT": (425000.0, 75000.0, 465000.0, 95000.0),
    "KENT": (535000.0, 95000.0, 665000.0, 185000.0),
    "LANCASHIRE": (325000.0, 400000.0, 390000.0, 465000.0),
    "LEICESTERSHIRE": (425000.0, 285000.0, 475000.0, 340000.0),
    "LINCOLNSHIRE": (475000.0, 330000.0, 560000.0, 400000.0),
    "MERSEYSIDE": (330000.0, 380000.0, 365000.0, 405000.0),
    "NORFOLK": (560000.0, 280000.0, 655000.0, 355000.0),
    "NORTH YORKSHIRE": (390000.0, 425000.0, 520000.0, 525000.0),
    "NORTHAMPTONSHIRE": (455000.0, 245000.0, 505000.0, 305000.0),
    "NORTHUMBERLAND": (380000.0, 550000.0, 430000.0, 665000.0),
    "NOTTINGHAMSHIRE": (445000.0, 330000.0, 485000.0, 390000.0),
    "OXFORDSHIRE": (425000.0, 185000.0, 485000.0, 245000.0),
    "RUTLAND": (485000.0, 295000.0, 505000.0, 315000.0),
    "SHROPSHIRE": (325000.0, 270000.0, 390000.0, 350000.0),
    "SOMERSET": (300000.0, 110000.0, 390000.0, 175000.0),
    "SOUTH YORKSHIRE": (420000.0, 375000.0, 475000.0, 410000.0),
    "STAFFORDSHIRE": (370000.0, 300000.0, 420000.0, 390000.0),
    "SUFFOLK": (555000.0, 235000.0, 655000.0, 300000.0),
    "SURREY": (485000.0, 125000.0, 535000.0, 180000.0),
    "TYNE AND WEAR": (415000.0, 555000.0, 445000.0, 585000.0),
    "WARWICKSHIRE": (390000.0, 240000.0, 450000.0, 310000.0),
    "WEST MIDLANDS": (380000.0, 275000.0, 435000.0, 315000.0),
    "WEST SUSSEX": (485000.0, 90000.0, 545000.0, 130000.0),
    "WEST YORKSHIRE": (390000.0, 405000.0, 455000.0, 455000.0),
    "WILTSHIRE": (380000.0, 130000.0, 430000.0, 200000.0),
    "WORCESTERSHIRE": (365000.0, 225000.0, 410000.0, 295000.0),
    "YORKSHIRE": (380000.0, 370000.0, 550000.0, 525000.0),
    # Scotland: tighter city/council extents for common ambiguity.
    "CITY OF EDINBURGH": (300000.0, 660000.0, 340000.0, 690000.0),
    "EAST LOTHIAN": (340000.0, 660000.0, 380000.0, 695000.0),
    "GLASGOW CITY": (245000.0, 650000.0, 280000.0, 680000.0),
    "MIDLOTHIAN": (300000.0, 650000.0, 340000.0, 675000.0),
    "WEST LOTHIAN": (285000.0, 655000.0, 315000.0, 690000.0),
})

ADMIN_BNG_EXTENTS.update({
    alias: ADMIN_BNG_EXTENTS[canonical]
    for alias, canonical in ADMIN_ALIASES.items()
    if canonical in ADMIN_BNG_EXTENTS
})
