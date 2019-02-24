
__all__ = [
        'IsoCountry',
        'isocountry',
        ]

iso_country_map = dict()

class IsoCountry(object):

    iso3166_1_alpha2 = None
    iso3166_1_alpha3 = None
    iso3166_1_num = None
    name = None

    def __str__(self):
        return self.iso3166_1_alpha2

    def __repr__(self):
        return '{}({!r})'.format(
            self.__class__.__name__,
            self.iso3166_1_alpha2)

    def __init__(self, iso3166_1_alpha2, iso3166_1_alpha3, iso3166_1_num, name, *, independent=None, user_assigned=None):
        self.iso3166_1_alpha2 = iso3166_1_alpha2 or None
        self.iso3166_1_alpha3 = iso3166_1_alpha3 or None
        self.iso3166_1_num = iso3166_1_num or None
        self.name = name or iso3166_1_alpha3 or iso3166_1_alpha2 or None
        assert self.name
        self.independent = independent
        self.user_assigned = user_assigned
        super().__init__()

    @property
    def code2(self):
        return self.iso3166_1_alpha2

    @property
    def code3(self):
        return self.iso3166_1_alpha3

    code = code2

    def __int__(self):
        return self.iso3166_1_num

    @property
    def map_keys(self):
        map_keys = set()
        for v in (
            self.name,
            self.code2,
            self.code3,
        ):
            if type(v) is str:
                v = v.lower()
            if v:
                map_keys.add(v)
        try:
            map_keys.add(int(self))
        except TypeError:
            pass
        return map_keys

def init_iso_country(iso3166_1_alpha2, iso3166_1_alpha3, iso3166_1_num, name, independent=None, user_assigned=None):
    country = IsoCountry(iso3166_1_alpha2, iso3166_1_alpha3, iso3166_1_num, name, independent=independent, user_assigned=user_assigned)
    for map_key in country.map_keys:
        iso_country_map[map_key] = country
    return country

init_iso_country('AD', 'AND', 20, 'Andorra Andorra', True)
init_iso_country('AE', 'ARE', 784, 'United Arab Emirates United Arab Emirates', True)
init_iso_country('AF', 'AFG', 4, 'Afghanistan Afghanistan', True)
init_iso_country('AG', 'ATG', 28, 'Antigua and Barbuda Antigua and Barbuda', True)
init_iso_country('AI', 'AIA', 660, 'Anguilla Anguilla', False)
init_iso_country('AL', 'ALB', 8, 'Albania Albania', True)
init_iso_country('AM', 'ARM', 51, 'Armenia Armenia', True)
init_iso_country('AO', 'AGO', 24, 'Angola Angola', True)
init_iso_country('AQ', 'ATA', 10, 'Antarctica Antarctica', False)
init_iso_country('AR', 'ARG', 32, 'Argentina Argentina', True)
init_iso_country('AS', 'ASM', 16, 'American Samoa American Samoa', False)
init_iso_country('AT', 'AUT', 40, 'Austria Austria', True)
init_iso_country('AU', 'AUS', 36, 'Australia Australia', True)
init_iso_country('AW', 'ABW', 533, 'Aruba Aruba', False)
init_iso_country('AX', 'ALA', 248, 'Åland Islands Åland Islands', False)
init_iso_country('AZ', 'AZE', 31, 'Azerbaijan Azerbaijan', True)
init_iso_country('BA', 'BIH', 70, 'Bosnia and Herzegovina Bosnia and Herzegovina', True)
init_iso_country('BB', 'BRB', 52, 'Barbados Barbados', True)
init_iso_country('BD', 'BGD', 50, 'Bangladesh Bangladesh', True)
init_iso_country('BE', 'BEL', 56, 'Belgium Belgium', True)
init_iso_country('BF', 'BFA', 854, 'Burkina Faso Burkina Faso', True)
init_iso_country('BG', 'BGR', 100, 'Bulgaria Bulgaria', True)
init_iso_country('BH', 'BHR', 48, 'Bahrain Bahrain', True)
init_iso_country('BI', 'BDI', 108, 'Burundi Burundi', True)
init_iso_country('BJ', 'BEN', 204, 'Benin Benin', True)
init_iso_country('BL', 'BLM', 652, 'Saint Barthélemy Saint Barthélemy', False)
init_iso_country('BM', 'BMU', 60, 'Bermuda Bermuda', False)
init_iso_country('BN', 'BRN', 96, 'Brunei Brunei Darussalam', True)
init_iso_country('BO', 'BOL', 68, 'Bolivia Bolivia (Plurinational State of)', True)
init_iso_country('BQ', 'BES', 535, 'Caribbean Netherlands Bonaire, Sint Eustatius and Saba', False)
init_iso_country('BR', 'BRA', 76, 'Brazil Brazil', True)
init_iso_country('BS', 'BHS', 44, 'The Bahamas Bahamas', True)
init_iso_country('BT', 'BTN', 64, 'Bhutan Bhutan', True)
init_iso_country('BV', 'BVT', 74, 'Bouvet Island Bouvet Island', False)
init_iso_country('BW', 'BWA', 72, 'Botswana Botswana', True)
init_iso_country('BY', 'BLR', 112, 'Belarus Belarus', True)
init_iso_country('BZ', 'BLZ', 84, 'Belize Belize', True)
init_iso_country('CA', 'CAN', 124, 'Canada Canada', True)
init_iso_country('CC', 'CCK', 166, 'Cocos (Keeling) Islands Cocos (Keeling) Islands', False)
init_iso_country('CD', 'COD', 180, 'Democratic Republic of the Congo Congo, Democratic Republic of the', True)
init_iso_country('CF', 'CAF', 140, 'Central African Republic Central African Republic', True)
init_iso_country('CG', 'COG', 178, 'Republic of the Congo Congo', True)
init_iso_country('CH', 'CHE', 756, 'Switzerland Switzerland', True)
init_iso_country('CI', 'CIV', 384, 'Ivory Coast Côte d\'Ivoire', True)
init_iso_country('CK', 'COK', 184, 'Cook Islands Cook Islands', False)
init_iso_country('CL', 'CHL', 152, 'Chile Chile', True)
init_iso_country('CM', 'CMR', 120, 'Cameroon Cameroon', True)
init_iso_country('CN', 'CHN', 156, 'China China', True)
init_iso_country('CO', 'COL', 170, 'Colombia Colombia', True)
init_iso_country('CR', 'CRI', 188, 'Costa Rica Costa Rica', True)
init_iso_country('CU', 'CUB', 192, 'Cuba Cuba', True)
init_iso_country('CV', 'CPV', 132, 'Cape Verde Cabo Verde', True)
init_iso_country('CW', 'CUW', 531, 'Curaçao Curaçao', False)
init_iso_country('CX', 'CXR', 162, 'Christmas Island Christmas Island', False)
init_iso_country('CY', 'CYP', 196, 'Cyprus Cyprus', True)
init_iso_country('CZ', 'CZE', 203, 'Czech Republic Czechia', True)
init_iso_country('DE', 'DEU', 276, 'Germany Germany', True)
init_iso_country('DJ', 'DJI', 262, 'Djibouti Djibouti', True)
init_iso_country('DK', 'DNK', 208, 'Denmark Denmark', True)
init_iso_country('DM', 'DMA', 212, 'Dominica Dominica', True)
init_iso_country('DO', 'DOM', 214, 'Dominican Republic Dominican Republic', True)
init_iso_country('DZ', 'DZA', 12, 'Algeria Algeria', True)
init_iso_country('EC', 'ECU', 218, 'Ecuador Ecuador', True)
init_iso_country('EE', 'EST', 233, 'Estonia Estonia', True)
init_iso_country('EG', 'EGY', 818, 'Egypt Egypt', True)
init_iso_country('EH', 'ESH', 732, 'Western Sahara Western Sahara', False)
init_iso_country('ER', 'ERI', 232, 'Eritrea Eritrea', True)
init_iso_country('ES', 'ESP', 724, 'Spain Spain', True)
init_iso_country('ET', 'ETH', 231, 'Ethiopia Ethiopia', True)
init_iso_country('FI', 'FIN', 246, 'Finland Finland', True)
init_iso_country('FJ', 'FJI', 242, 'Fiji Fiji', True)
init_iso_country('FK', 'FLK', 238, 'Falkland Islands Falkland Islands (Malvinas)', False)
init_iso_country('FM', 'FSM', 583, 'Federated States of Micronesia Micronesia (Federated States of)', True)
init_iso_country('FO', 'FRO', 234, 'Faroe Islands Faroe Islands', False)
init_iso_country('FR', 'FRA', 250, 'France France', True)
init_iso_country('GA', 'GAB', 266, 'Gabon Gabon', True)
init_iso_country('GB', 'GBR', 826, 'United Kingdom United Kingdom of Great Britain and Northern Ireland', True)
init_iso_country('GD', 'GRD', 308, 'Grenada Grenada', True)
init_iso_country('GE', 'GEO', 268, 'Georgia (country) Georgia', True)
init_iso_country('GF', 'GUF', 254, 'French Guiana French Guiana', False)
init_iso_country('GG', 'GGY', 831, 'Guernsey Guernsey', False)
init_iso_country('GH', 'GHA', 288, 'Ghana Ghana', True)
init_iso_country('GI', 'GIB', 292, 'Gibraltar Gibraltar', False)
init_iso_country('GL', 'GRL', 304, 'Greenland Greenland', False)
init_iso_country('GM', 'GMB', 270, 'The Gambia Gambia', True)
init_iso_country('GN', 'GIN', 324, 'Guinea Guinea', True)
init_iso_country('GP', 'GLP', 312, 'Guadeloupe Guadeloupe', False)
init_iso_country('GQ', 'GNQ', 226, 'Equatorial Guinea Equatorial Guinea', True)
init_iso_country('GR', 'GRC', 300, 'Greece Greece', True)
init_iso_country('GS', 'SGS', 239, 'South Georgia and the South Sandwich Islands South Georgia and the South Sandwich Islands', False)
init_iso_country('GT', 'GTM', 320, 'Guatemala Guatemala', True)
init_iso_country('GU', 'GUM', 316, 'Guam Guam', False)
init_iso_country('GW', 'GNB', 624, 'Guinea-Bissau Guinea-Bissau', True)
init_iso_country('GY', 'GUY', 328, 'Guyana Guyana', True)
init_iso_country('HK', 'HKG', 344, 'Hong Kong Hong Kong', False)
init_iso_country('HM', 'HMD', 334, 'Heard Island and McDonald Islands Heard Island and McDonald Islands', False)
init_iso_country('HN', 'HND', 340, 'Honduras Honduras', True)
init_iso_country('HR', 'HRV', 191, 'Croatia Croatia', True)
init_iso_country('HT', 'HTI', 332, 'Haiti Haiti', True)
init_iso_country('HU', 'HUN', 348, 'Hungary Hungary', True)
init_iso_country('ID', 'IDN', 360, 'Indonesia Indonesia', True)
init_iso_country('IE', 'IRL', 372, 'Republic of Ireland Ireland', True)
init_iso_country('IL', 'ISR', 376, 'Israel Israel', True)
init_iso_country('IM', 'IMN', 833, 'Isle of Man Isle of Man', False)
init_iso_country('IN', 'IND', 356, 'India India', True)
init_iso_country('IO', 'IOT', 86, 'British Indian Ocean Territory British Indian Ocean Territory', False)
init_iso_country('IQ', 'IRQ', 368, 'Iraq Iraq', True)
init_iso_country('IR', 'IRN', 364, 'Iran Iran (Islamic Republic of)', True)
init_iso_country('IS', 'ISL', 352, 'Iceland Iceland', True)
init_iso_country('IT', 'ITA', 380, 'Italy Italy', True)
init_iso_country('JE', 'JEY', 832, 'Jersey Jersey', False)
init_iso_country('JM', 'JAM', 388, 'Jamaica Jamaica', True)
init_iso_country('JO', 'JOR', 400, 'Jordan Jordan', True)
init_iso_country('JP', 'JPN', 392, 'Japan Japan', True)
init_iso_country('KE', 'KEN', 404, 'Kenya Kenya', True)
init_iso_country('KG', 'KGZ', 417, 'Kyrgyzstan Kyrgyzstan', True)
init_iso_country('KH', 'KHM', 116, 'Cambodia Cambodia', True)
init_iso_country('KI', 'KIR', 296, 'Kiribati Kiribati', True)
init_iso_country('KM', 'COM', 174, 'Comoros Comoros', True)
init_iso_country('KN', 'KNA', 659, 'Saint Kitts and Nevis Saint Kitts and Nevis', True)
init_iso_country('KP', 'PRK', 408, 'North Korea Korea (Democratic People\'s Republic of)', True)
init_iso_country('KR', 'KOR', 410, 'South Korea Korea, Republic of', True)
init_iso_country('KW', 'KWT', 414, 'Kuwait Kuwait', True)
init_iso_country('KY', 'CYM', 136, 'Cayman Islands Cayman Islands', False)
init_iso_country('KZ', 'KAZ', 398, 'Kazakhstan Kazakhstan', True)
init_iso_country('LA', 'LAO', 418, 'Laos Lao People\'s Democratic Republic', True)
init_iso_country('LB', 'LBN', 422, 'Lebanon Lebanon', True)
init_iso_country('LC', 'LCA', 662, 'Saint Lucia Saint Lucia', True)
init_iso_country('LI', 'LIE', 438, 'Liechtenstein Liechtenstein', True)
init_iso_country('LK', 'LKA', 144, 'Sri Lanka Sri Lanka', True)
init_iso_country('LR', 'LBR', 430, 'Liberia Liberia', True)
init_iso_country('LS', 'LSO', 426, 'Lesotho Lesotho', True)
init_iso_country('LT', 'LTU', 440, 'Lithuania Lithuania', True)
init_iso_country('LU', 'LUX', 442, 'Luxembourg Luxembourg', True)
init_iso_country('LV', 'LVA', 428, 'Latvia Latvia', True)
init_iso_country('LY', 'LBY', 434, 'Libya Libya', True)
init_iso_country('MA', 'MAR', 504, 'Morocco Morocco', True)
init_iso_country('MC', 'MCO', 492, 'Monaco Monaco', True)
init_iso_country('MD', 'MDA', 498, 'Moldova Moldova, Republic of', True)
init_iso_country('ME', 'MNE', 499, 'Montenegro Montenegro', True)
init_iso_country('MF', 'MAF', 663, 'Collectivity of Saint Martin Saint Martin (French part)', False)
init_iso_country('MG', 'MDG', 450, 'Madagascar Madagascar', True)
init_iso_country('MH', 'MHL', 584, 'Marshall Islands Marshall Islands', True)
init_iso_country('MK', 'MKD', 807, 'Republic of Macedonia Macedonia, the former Yugoslav Republic of', True)
init_iso_country('ML', 'MLI', 466, 'Mali Mali', True)
init_iso_country('MM', 'MMR', 104, 'Myanmar Myanmar', True)
init_iso_country('MN', 'MNG', 496, 'Mongolia Mongolia', True)
init_iso_country('MO', 'MAC', 446, 'Macau Macao', False)
init_iso_country('MP', 'MNP', 580, 'Northern Mariana Islands Northern Mariana Islands', False)
init_iso_country('MQ', 'MTQ', 474, 'Martinique Martinique', False)
init_iso_country('MR', 'MRT', 478, 'Mauritania Mauritania', True)
init_iso_country('MS', 'MSR', 500, 'Montserrat Montserrat', False)
init_iso_country('MT', 'MLT', 470, 'Malta Malta', True)
init_iso_country('MU', 'MUS', 480, 'Mauritius Mauritius', True)
init_iso_country('MV', 'MDV', 462, 'Maldives Maldives', True)
init_iso_country('MW', 'MWI', 454, 'Malawi Malawi', True)
init_iso_country('MX', 'MEX', 484, 'Mexico Mexico', True)
init_iso_country('MY', 'MYS', 458, 'Malaysia Malaysia', True)
init_iso_country('MZ', 'MOZ', 508, 'Mozambique Mozambique', True)
init_iso_country('NA', 'NAM', 516, 'Namibia Namibia', True)
init_iso_country('NC', 'NCL', 540, 'New Caledonia New Caledonia', False)
init_iso_country('NE', 'NER', 562, 'Niger Niger', True)
init_iso_country('NF', 'NFK', 574, 'Norfolk Island Norfolk Island', False)
init_iso_country('NG', 'NGA', 566, 'Nigeria Nigeria', True)
init_iso_country('NI', 'NIC', 558, 'Nicaragua Nicaragua', True)
init_iso_country('NL', 'NLD', 528, 'Netherlands Netherlands', True)
init_iso_country('NO', 'NOR', 578, 'Norway Norway', True)
init_iso_country('NP', 'NPL', 524, 'Nepal Nepal', True)
init_iso_country('NR', 'NRU', 520, 'Nauru Nauru', True)
init_iso_country('NU', 'NIU', 570, 'Niue Niue', False)
init_iso_country('NZ', 'NZL', 554, 'New Zealand New Zealand', True)
init_iso_country('OM', 'OMN', 512, 'Oman Oman', True)
init_iso_country('PA', 'PAN', 591, 'Panama Panama', True)
init_iso_country('PE', 'PER', 604, 'Peru Peru', True)
init_iso_country('PF', 'PYF', 258, 'French Polynesia French Polynesia', False)
init_iso_country('PG', 'PNG', 598, 'Papua New Guinea Papua New Guinea', True)
init_iso_country('PH', 'PHL', 608, 'Philippines Philippines', True)
init_iso_country('PK', 'PAK', 586, 'Pakistan Pakistan', True)
init_iso_country('PL', 'POL', 616, 'Poland Poland', True)
init_iso_country('PM', 'SPM', 666, 'Saint Pierre and Miquelon Saint Pierre and Miquelon', False)
init_iso_country('PN', 'PCN', 612, 'Pitcairn Islands Pitcairn', False)
init_iso_country('PR', 'PRI', 630, 'Puerto Rico Puerto Rico', False)
init_iso_country('PS', 'PSE', 275, 'State of Palestine Palestine, State of', False)
init_iso_country('PT', 'PRT', 620, 'Portugal Portugal', True)
init_iso_country('PW', 'PLW', 585, 'Palau Palau', True)
init_iso_country('PY', 'PRY', 600, 'Paraguay Paraguay', True)
init_iso_country('QA', 'QAT', 634, 'Qatar Qatar', True)
init_iso_country('RE', 'REU', 638, 'Réunion Réunion', False)
init_iso_country('RO', 'ROU', 642, 'Romania Romania', True)
init_iso_country('RS', 'SRB', 688, 'Serbia Serbia', True)
init_iso_country('RU', 'RUS', 643, 'Russia Russian Federation', True)
init_iso_country('RW', 'RWA', 646, 'Rwanda Rwanda', True)
init_iso_country('SA', 'SAU', 682, 'Saudi Arabia Saudi Arabia', True)
init_iso_country('SB', 'SLB', 90, 'Solomon Islands Solomon Islands', True)
init_iso_country('SC', 'SYC', 690, 'Seychelles Seychelles', True)
init_iso_country('SD', 'SDN', 729, 'Sudan Sudan', True)
init_iso_country('SE', 'SWE', 752, 'Sweden Sweden', True)
init_iso_country('SG', 'SGP', 702, 'Singapore Singapore', True)
init_iso_country('SH', 'SHN', 654, 'Saint Helena, Ascension and Tristan da Cunha Saint Helena, Ascension and Tristan da Cunha', False)
init_iso_country('SI', 'SVN', 705, 'Slovenia Slovenia', True)
init_iso_country('SJ', 'SJM', 744, 'Svalbard and Jan Mayen Svalbard and Jan Mayen', False)
init_iso_country('SK', 'SVK', 703, 'Slovakia Slovakia', True)
init_iso_country('SL', 'SLE', 694, 'Sierra Leone Sierra Leone', True)
init_iso_country('SM', 'SMR', 674, 'San Marino San Marino', True)
init_iso_country('SN', 'SEN', 686, 'Senegal Senegal', True)
init_iso_country('SO', 'SOM', 706, 'Somalia Somalia', True)
init_iso_country('SR', 'SUR', 740, 'Suriname Suriname', True)
init_iso_country('SS', 'SSD', 728, 'South Sudan South Sudan', True)
init_iso_country('ST', 'STP', 678, 'São Tomé and Príncipe Sao Tome and Principe', True)
init_iso_country('SV', 'SLV', 222, 'El Salvador El Salvador', True)
init_iso_country('SX', 'SXM', 534, 'Sint Maarten Sint Maarten (Dutch part)', False)
init_iso_country('SY', 'SYR', 760, 'Syria Syrian Arab Republic', True)
init_iso_country('SZ', 'SWZ', 748, 'Eswatini Eswatini', True)
init_iso_country('TC', 'TCA', 796, 'Turks and Caicos Islands Turks and Caicos Islands', False)
init_iso_country('TD', 'TCD', 148, 'Chad Chad', True)
init_iso_country('TF', 'ATF', 260, 'French Southern and Antarctic Lands French Southern Territories', False)
init_iso_country('TG', 'TGO', 768, 'Togo Togo', True)
init_iso_country('TH', 'THA', 764, 'Thailand Thailand', True)
init_iso_country('TJ', 'TJK', 762, 'Tajikistan Tajikistan', True)
init_iso_country('TK', 'TKL', 772, 'Tokelau Tokelau', False)
init_iso_country('TL', 'TLS', 626, 'East Timor Timor-Leste', True)
init_iso_country('TM', 'TKM', 795, 'Turkmenistan Turkmenistan', True)
init_iso_country('TN', 'TUN', 788, 'Tunisia Tunisia', True)
init_iso_country('TO', 'TON', 776, 'Tonga Tonga', True)
init_iso_country('TR', 'TUR', 792, 'Turkey Turkey', True)
init_iso_country('TT', 'TTO', 780, 'Trinidad and Tobago Trinidad and Tobago', True)
init_iso_country('TV', 'TUV', 798, 'Tuvalu Tuvalu', True)
init_iso_country('TW', 'TWN', 158, 'Taiwan Taiwan, Province of China[a]', False)
init_iso_country('TZ', 'TZA', 834, 'Tanzania Tanzania, United Republic of', True)
init_iso_country('UA', 'UKR', 804, 'Ukraine Ukraine', True)
init_iso_country('UG', 'UGA', 800, 'Uganda Uganda', True)
init_iso_country('UM', 'UMI', 581, 'United States Minor Outlying Islands United States Minor Outlying Islands', False)
init_iso_country('US', 'USA', 840, 'United States United States of America', True)
init_iso_country('UY', 'URY', 858, 'Uruguay Uruguay', True)
init_iso_country('UZ', 'UZB', 860, 'Uzbekistan Uzbekistan', True)
init_iso_country('VA', 'VAT', 336, 'Vatican City Holy See', True)
init_iso_country('VC', 'VCT', 670, 'Saint Vincent and the Grenadines Saint Vincent and the Grenadines', True)
init_iso_country('VE', 'VEN', 862, 'Venezuela Venezuela (Bolivarian Republic of)', True)
init_iso_country('VG', 'VGB', 92, 'British Virgin Islands Virgin Islands (British)', False)
init_iso_country('VI', 'VIR', 850, 'United States Virgin Islands Virgin Islands (U.S.)', False)
init_iso_country('VN', 'VNM', 704, 'Vietnam Viet Nam', True)
init_iso_country('VU', 'VUT', 548, 'Vanuatu Vanuatu', True)
init_iso_country('WF', 'WLF', 876, 'Wallis and Futuna Wallis and Futuna', False)
init_iso_country('WS', 'WSM', 882, 'Samoa Samoa', True)
init_iso_country('YE', 'YEM', 887, 'Yemen Yemen', True)
init_iso_country('YT', 'MYT', 175, 'Mayotte Mayotte', False)
init_iso_country('ZA', 'ZAF', 710, 'South Africa South Africa', True)
init_iso_country('ZM', 'ZMB', 894, 'Zambia Zambia', True)
init_iso_country('ZW', 'ZWE', 716, 'Zimbabwe Zimbabwe', True)

# https://musicbrainz.org/doc/Release_Country
init_iso_country('XE', None, None, 'Europe (Specific country unknown)', user_assigned='MusicBrainz')
init_iso_country('XW', None, None, 'Worldwide', user_assigned='MusicBrainz')
init_iso_country('XU', None, None, 'Unknown', user_assigned='MusicBrainz')
#AN	Netherlands Antilles	
#CS	Serbia and Montenegro	Historical, February 2003 - June 2006 (3166-3 CSXX)
#SU	Soviet Union	Historical, 1922 - 1991 (3166-3 SUHH)
#SZ	Swaziland	
#XC	Czechoslovakia	Historical, October 1918 - January 1992 (3166-3 CSHH)
#XG	East Germany	Historical, 1949 - 1990 (3166-3 DDDE)

# https://en.wikipedia.org/wiki/ISO_3166-3
# Former country name	Former codes	Period of validity	ISO 3166-3 code	New country names and codes
# British Antarctic Territory	BQ, ATB,  -	19741979	BQAQ	Merged into Antarctica (AQ, ATA, 010)
# Burma	BU, BUR, 104	19741989	BUMM	Name changed to Myanmar (MM, MMR, 104)
# Byelorussian SSR	BY, BYS, 112	19741992	BYAA	Name changed to Belarus (BY, BLR, 112)
# Canton and Enderbury Islands	CT, CTE, 128	19741984	CTKI	Merged into Kiribati (KI, KIR, 296)
# Czechoslovakia	CS, CSK, 200	19741993	CSHH
# 	Divided into:
# Czech Republic (CZ, CZE, 203)
# Slovakia (SK, SVK, 703)
# Dahomey	DY, DHY, 204	19741977	DYBJ	Name changed to Benin (BJ, BEN, 204)
# Dronning Maud Land	NQ, ATN, 216	19741983	NQAQ	Merged into Antarctica (AQ, ATA, 010)
# East Timor [note 1]	TP, TMP, 626	19742002	TPTL	Name changed to Timor-Leste (TL, TLS, 626)
# France, Metropolitan	FX, FXX, 249	19931997	FXFR	Merged into France (FR, FRA, 250)
# French Afars and Issas	AI, AFI, 262	19741977	AIDJ	Name changed to Djibouti (DJ, DJI, 262)
# French Southern and Antarctic Territories	FQ, ATF,  -	19741979	FQHH	Divided into:
# Part of Antarctica (AQ, ATA, 010) (i.e., Adélie Land)
# French Southern Territories (TF, ATF, 260)
# German Democratic Republic	DD, DDR, 278	19741990	DDDE	Merged into Germany (DE, DEU, 276)
# Gilbert and Ellice Islands	GE, GEL, 296	19741979	GEHH	Divided into:
# Kiribati (KI, KIR, 296)
# Tuvalu (TV, TUV, 798)
# Johnston Island	JT, JTN, 396	19741986	JTUM	Merged into United States Minor Outlying Islands (UM, UMI, 581)
# Midway Islands	MI, MID, 488	19741986	MIUM	Merged into United States Minor Outlying Islands (UM, UMI, 581)
# Netherlands Antilles	AN, ANT, 530
# [note 2]	19742010 [note 3]	ANHH	Divided into:
# Bonaire, Sint Eustatius and Saba (BQ, BES, 535) [note 4]
# Curaçao (CW, CUW, 531)
# Sint Maarten (Dutch part) (SX, SXM, 534)
# Neutral Zone	NT, NTZ, 536	19741993	NTHH	Divided into:
# Part of Iraq (IQ, IRQ, 368)
# Part of Saudi Arabia (SA, SAU, 682)
# New Hebrides	NH, NHB, 548	19741980	NHVU	Name changed to Vanuatu (VU, VUT, 548)
# Pacific Islands (Trust Territory)	PC, PCI, 582	19741986	PCHH	Divided into:
# Marshall Islands (MH, MHL, 584)
# Micronesia, Federated States of (FM, FSM, 583)
# Northern Mariana Islands (MP, MNP, 580)
# Palau (PW, PLW, 585)
# Panama Canal Zone	PZ, PCZ,  -	19741980	PZPA	Merged into Panama (PA, PAN, 591)
# Serbia and Montenegro	CS, SCG, 891	20032006	CSXX
# [note 5]	Divided into:
# Montenegro (ME, MNE, 499)
# Serbia (RS, SRB, 688)
# Sikkim	SK, SKM,  -	19741975	SKIN	Merged into India (IN, IND, 356)
# Southern Rhodesia	RH, RHO, 716	19741980	RHZW	Name changed to Zimbabwe (ZW, ZWE, 716)
# United States Miscellaneous Pacific Islands	PU, PUS, 849	19741986	PUUM	Merged into United States Minor Outlying Islands (UM, UMI, 581)
# Upper Volta	HV, HVO, 854	19741984	HVBF	Name changed to Burkina Faso (BF, BFA, 854)
# USSR	SU, SUN, 810	19741992	SUHH	Divided into: [note 6]
# Armenia (AM, ARM, 051)
# Azerbaijan (AZ, AZE, 031)
# Estonia (EE, EST, 233)
# Georgia (GE, GEO, 268)
# Kazakhstan (KZ, KAZ, 398)
# Kyrgyzstan (KG, KGZ, 417)
# Latvia (LV, LVA, 428)
# Lithuania (LT, LTU, 440)
# Moldova, Republic of (MD, MDA, 498)
# Russian Federation (RU, RUS, 643)
# Tajikistan (TJ, TJK, 762)
# Turkmenistan (TM, TKM, 795)
# Uzbekistan (UZ, UZB, 860)
# Viet-Nam, Democratic Republic of	VD, VDR,  -	19741977	VDVN	Merged into Viet Nam (VN, VNM, 704)
# Wake Island	WK, WAK, 872	19741986	WKUM	Merged into United States Minor Outlying Islands (UM, UMI, 581)
# Yemen, Democratic	YD, YMD, 720	19741990	YDYE	Merged into Yemen (YE, YEM, 887)
# Yugoslavia	YU, YUG, 891
# [note 7]	19742003	YUCS	Name changed to Serbia and Montenegro (CS, SCG, 891)
# Zaire	ZR, ZAR, 180	19741997	ZRCD	Name changed to Congo, the Democratic Republic of the (CD, COD, 180)

def isocountry(v):
    if type(v) is str:
        try:
            return iso_country_map[v.lower()]
        except KeyError:
            raise ValueError('Unrecognized country code %r' % (v,))
    elif isinstance(v, IsoCountry):
        return v  # Unique!
    else:
        raise TypeError(v)

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
