"""One-time script to add brand_awareness field to all persona JSON files."""
import json
from pathlib import Path

PERSONAS_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "SEEDS" / "personas_v2"

# Brand awareness definitions per persona
BRAND_AWARENESS = {
    "persona_beauty_001": {
        # 林雪 28F 上海 互联网产品经理 25k 成分党
        "well_known": ["雅诗兰黛", "兰蔻", "欧莱雅", "SK-II", "资生堂", "修丽可", "The Ordinary", "珀莱雅", "薇诺娜", "理肤泉", "雅漾", "倩碧", "玉兰油", "百雀羚", "自然堂"],
        "heard_of": ["赫莲娜", "CPB", "海蓝之谜", "Drunk Elephant", "至本", "PMPM", "HBN", "溪木源", "花西子", "完美日记", "韩束", "丸美", "欧诗漫", "妮维雅"],
        "vague_or_unknown": ["蛤蜊油", "友谊雪花膏", "隆力奇", "肌司研"],
        "awareness_rule": "成分党，对国际品牌和新锐成分品牌都很熟，小红书/B站上讨论过的品牌基本都知道"
    },
    "persona_beauty_002": {
        # 陈婷婷 34F 成都 全职妈妈 9k
        "well_known": ["欧莱雅", "兰蔻", "玉兰油", "自然堂", "珀莱雅", "百雀羚", "大宝", "妮维雅", "雅诗兰黛", "SK-II", "资生堂", "韩束", "相宜本草"],
        "heard_of": ["薇诺娜", "玉泽", "花西子", "完美日记", "理肤泉", "雅漾", "倩碧", "海蓝之谜", "丸美", "欧诗漫"],
        "vague_or_unknown": ["修丽可", "The Ordinary", "Drunk Elephant", "至本", "PMPM", "HBN", "溪木源", "CPB", "赫莲娜"],
        "awareness_rule": "认识主流大牌和超市常见品牌，新锐线上品牌不太了解，高端小众品牌只听过名字"
    },
    "persona_beauty_003": {
        # 周曼 23F 广州 美妆集合店导购 7.5k
        "well_known": ["花西子", "完美日记", "橘朵", "3CE", "珀莱雅", "欧莱雅", "兰蔻", "雅诗兰黛", "MAC", "迪奥", "自然堂", "韩束", "百雀羚", "薇诺娜", "SK-II", "资生堂"],
        "heard_of": ["修丽可", "理肤泉", "雅漾", "海蓝之谜", "倩碧", "至本", "PMPM", "HBN", "丸美", "玉兰油", "Drunk Elephant", "妮维雅", "半亩花田"],
        "vague_or_unknown": ["CPB", "赫莲娜", "The Ordinary", "Mama&Kids", "蛤蜊油", "隆力奇"],
        "awareness_rule": "美妆集合店导购，对彩妆和大众护肤品牌非常熟，高端贵妇线了解有限，新锐国货很熟"
    },
    "persona_beauty_004": {
        # 王佳怡 20F 武汉 大学生 2.5k
        "well_known": ["珀莱雅", "薇诺娜", "橘朵", "花西子", "完美日记", "欧莱雅", "自然堂", "百雀羚", "大宝", "妮维雅", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["瑷尔博士", "至本", "PMPM", "理肤泉", "雅漾", "韩束", "丸美", "半亩花田", "资生堂", "倩碧", "HBN", "溪木源", "MAC"],
        "vague_or_unknown": ["修丽可", "CPB", "赫莲娜", "海蓝之谜", "Drunk Elephant", "The Ordinary", "Mama&Kids", "隆力奇"],
        "awareness_rule": "大学生，小红书重度用户，熟悉平价和学生党品牌，国际大牌知道名字但没用过，高端线不了解"
    },
    "persona_beauty_005": {
        # 刘骁 31M 杭州 电商运营经理 18k
        "well_known": ["欧莱雅", "兰蔻", "雅诗兰黛", "SK-II", "珀莱雅", "花西子", "完美日记", "薇诺娜", "韩束", "自然堂", "百雀羚", "妮维雅", "理肤泉", "资生堂", "大宝"],
        "heard_of": ["修丽可", "雅漾", "至本", "PMPM", "HBN", "碧欧泉", "曼秀雷敦", "丸美", "倩碧", "海蓝之谜", "半亩花田", "溪木源", "玉兰油"],
        "vague_or_unknown": ["CPB", "赫莲娜", "Drunk Elephant", "The Ordinary", "Mama&Kids"],
        "awareness_rule": "电商从业者，对各价位段品牌都有认知，尤其熟悉天猫热卖品牌和国货新锐，高端贵妇线了解较少"
    },
    "persona_beauty_006": {
        # 张薇 37F 北京 外企市场总监 38k
        "well_known": ["雅诗兰黛", "兰蔻", "赫莲娜", "海蓝之谜", "SK-II", "资生堂", "CPB", "迪奥", "香奈儿", "修丽可", "欧莱雅", "倩碧", "玉兰油", "百雀羚", "自然堂", "薇诺娜", "珀莱雅"],
        "heard_of": ["Drunk Elephant", "La Mer", "Aesop", "理肤泉", "雅漾", "花西子", "完美日记", "韩束", "PMPM", "至本", "丸美", "妮维雅", "大宝"],
        "vague_or_unknown": ["肌司研", "半亩花田", "蛤蜊油", "隆力奇", "温碧泉", "理然", "亲爱男友"],
        "awareness_rule": "高收入外企高管，国际大牌和高端线非常熟，国货主流品牌也认识，下沉市场品牌和男士新锐不了解"
    },
    "persona_beauty_007": {
        # 赵小萌 22F 临沂 奶茶店店员 4.5k T3
        "well_known": ["花西子", "完美日记", "珀莱雅", "自然堂", "百雀羚", "欧莱雅", "大宝", "妮维雅", "韩束", "玉兰油", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["薇诺娜", "半亩花田", "橘朵", "至本", "丸美", "相宜本草", "资生堂", "倩碧", "理肤泉", "欧诗漫"],
        "vague_or_unknown": ["修丽可", "赫莲娜", "CPB", "海蓝之谜", "The Ordinary", "Drunk Elephant", "PMPM", "HBN", "Aesop"],
        "awareness_rule": "三线城市年轻女生，熟悉抖音/小红书热门平价品牌和超市常见品牌，知道国际大牌名字但没用过，小众高端完全不了解"
    },
    "persona_beauty_008": {
        # 孙雨桐 27F 南京 初中英语老师 9.5k 敏感肌
        "well_known": ["薇诺娜", "理肤泉", "雅漾", "珂润", "欧莱雅", "兰蔻", "雅诗兰黛", "SK-II", "资生堂", "倩碧", "百雀羚", "自然堂", "珀莱雅", "大宝", "妮维雅", "玉兰油"],
        "heard_of": ["修丽可", "至本", "玉泽", "芙丽芳丝", "花西子", "完美日记", "韩束", "丸美", "海蓝之谜", "PMPM", "HBN", "相宜本草"],
        "vague_or_unknown": ["CPB", "赫莲娜", "Drunk Elephant", "The Ordinary", "Aesop", "理然", "肌司研"],
        "awareness_rule": "敏感肌用户，对药妆和敏感肌品牌特别熟，主流品牌都认识，高端贵妇线和男士品牌不了解"
    },
    "persona_beauty_009": {
        # 何建国 45M 郑州 国企中层 15k
        "well_known": ["大宝", "妮维雅", "欧莱雅", "玉兰油", "百雀羚", "自然堂", "兰蔻", "雅诗兰黛", "SK-II", "资生堂", "倩碧"],
        "heard_of": ["珀莱雅", "韩束", "相宜本草", "海蓝之谜", "迪奥", "香奈儿", "薇诺娜", "丸美"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "Drunk Elephant", "理然", "溪木源"],
        "awareness_rule": "中年男性，只认超市常见品牌和老婆用的大牌，新锐国货和成分党品牌完全不了解"
    },
    "persona_beauty_010": {
        # 李思涵 30F 苏州 产假UI设计师 12k
        "well_known": ["欧莱雅", "兰蔻", "雅诗兰黛", "SK-II", "资生堂", "倩碧", "珀莱雅", "薇诺娜", "百雀羚", "自然堂", "大宝", "妮维雅", "玉兰油", "理肤泉", "雅漾"],
        "heard_of": ["嫩芙", "Mama&Kids", "芙丽芳丝", "Fresh", "修丽可", "花西子", "完美日记", "韩束", "至本", "PMPM", "玉泽", "海蓝之谜", "丸美"],
        "vague_or_unknown": ["CPB", "赫莲娜", "Drunk Elephant", "The Ordinary", "理然", "Aesop", "肌司研"],
        "awareness_rule": "孕期妈妈，对母婴安全品牌有特别关注，主流品牌都认识，高端小众和男士品牌不太了解"
    },
    "persona_beauty_011": {
        # 吴晓蕾 29F 深圳 金融分析师 30k 医美
        "well_known": ["修丽可", "薇诺娜", "可复美", "创福康", "雅诗兰黛", "兰蔻", "SK-II", "资生堂", "欧莱雅", "理肤泉", "雅漾", "海蓝之谜", "倩碧", "赫莲娜", "珀莱雅"],
        "heard_of": ["CPB", "Drunk Elephant", "至本", "PMPM", "花西子", "完美日记", "百雀羚", "自然堂", "韩束", "玉泽", "HBN", "The Ordinary"],
        "vague_or_unknown": ["大宝", "隆力奇", "蛤蜊油", "友谊雪花膏", "肌司研", "温碧泉"],
        "awareness_rule": "医美用户+高收入，对医美术后品牌和高端护肤非常熟，主流品牌都认识，下沉市场品牌不了解"
    },
    "persona_beauty_012": {
        # 郑秀兰 56F 济南 退休小学教师 6.5k T2
        "well_known": ["大宝", "百雀羚", "玉兰油", "隆力奇", "自然堂", "欧莱雅", "妮维雅", "相宜本草", "雅诗兰黛", "兰蔻", "SK-II", "资生堂"],
        "heard_of": ["珀莱雅", "韩束", "丸美", "倩碧", "玉泽", "海蓝之谜", "薇诺娜"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "Drunk Elephant", "CPB", "赫莲娜", "溪木源"],
        "awareness_rule": "退休老人，非常熟悉超市和药店品牌，知道国际大牌名字，新锐线上品牌和高端小众完全不了解"
    },
    "persona_beauty_013": {
        # 苏瑶 27F 上海 4A广告策划 20k 审美驱动
        "well_known": ["Drunk Elephant", "Aesop", "La Mer", "SK-II", "雅诗兰黛", "兰蔻", "迪奥", "香奈儿", "资生堂", "CPB", "赫莲娜", "修丽可", "欧莱雅", "倩碧", "珀莱雅", "薇诺娜"],
        "heard_of": ["至本", "PMPM", "HBN", "花西子", "完美日记", "百雀羚", "自然堂", "理肤泉", "雅漾", "The Ordinary", "溪木源", "韩束"],
        "vague_or_unknown": ["大宝", "隆力奇", "蛤蜊油", "友谊雪花膏", "温碧泉", "肌司研"],
        "awareness_rule": "广告行业+审美驱动，对高端品牌和设计感品牌非常熟，主流品牌都认识，下沉市场和老牌国货不了解"
    },
    "persona_beauty_014": {
        # 黄丽芳 35F 宜春 小超市老板娘 8k T4
        "well_known": ["珀莱雅", "自然堂", "韩束", "欧诗漫", "百雀羚", "大宝", "妮维雅", "玉兰油", "欧莱雅", "相宜本草", "丸美", "温碧泉", "兰蔻", "雅诗兰黛"],
        "heard_of": ["SK-II", "薇诺娜", "花西子", "完美日记", "资生堂", "倩碧", "隆力奇", "半亩花田"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "HBN", "The Ordinary", "CPB", "赫莲娜", "Drunk Elephant", "海蓝之谜", "Aesop"],
        "awareness_rule": "四线城市超市老板娘，非常熟悉超市渠道和抖音直播间品牌，知道几个大牌名字，线上新锐和高端小众完全不了解"
    },
    "persona_beauty_015": {
        # 杨子墨 19M 成都 大一传媒 3k
        "well_known": ["理然", "亲爱男友", "至本", "PMPM", "欧莱雅", "妮维雅", "珀莱雅", "花西子", "完美日记", "兰蔻", "雅诗兰黛", "SK-II", "大宝"],
        "heard_of": ["修丽可", "薇诺娜", "半亩花田", "HBN", "溪木源", "橘朵", "3CE", "百雀羚", "自然堂", "韩束", "资生堂"],
        "vague_or_unknown": ["CPB", "赫莲娜", "海蓝之谜", "Drunk Elephant", "隆力奇", "友谊雪花膏", "蛤蜊油", "相宜本草", "丸美"],
        "awareness_rule": "Z世代男生，B站/小红书/得物重度用户，熟悉男士新锐和年轻人品牌，知道大牌名字，老牌国货和贵妇线不了解"
    },
    "persona_beauty_016": {
        # 王大强 48M 洛阳 建材店老板 20k T3
        "well_known": ["兰蔻", "雅诗兰黛", "SK-II", "迪奥", "香奈儿", "欧莱雅", "玉兰油", "大宝", "妮维雅", "资生堂", "百雀羚", "自然堂"],
        "heard_of": ["珀莱雅", "倩碧", "海蓝之谜", "韩束", "薇诺娜", "丸美", "相宜本草"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "CPB", "赫莲娜", "Drunk Elephant", "理然"],
        "awareness_rule": "中年男性老板，熟悉送礼常见的大牌和超市品牌，新锐国货和年轻人品牌完全不了解"
    },
    "persona_beauty_017": {
        # 刘美珍 50F 六安 乡镇卫生院护士 5.5k T4
        "well_known": ["百雀羚", "大宝", "相宜本草", "妮维雅", "玉兰油", "自然堂", "珀莱雅", "欧莱雅", "隆力奇"],
        "heard_of": ["韩束", "丸美", "温碧泉", "兰蔻", "雅诗兰黛", "SK-II", "欧诗漫", "薇诺娜"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "CPB", "赫莲娜", "海蓝之谜", "Drunk Elephant", "资生堂"],
        "awareness_rule": "乡镇中年女性，只认超市和药店能买到的品牌，国际大牌只听过名字，线上品牌和高端品牌不了解"
    },
    "persona_beauty_018": {
        # 陈志远 33M 长沙 健身教练 12k T2
        "well_known": ["欧莱雅", "妮维雅", "大宝", "理然", "珀莱雅", "自然堂", "百雀羚", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["至本", "PMPM", "薇诺娜", "碧欧泉", "曼秀雷敦", "韩束", "花西子", "倩碧", "资生堂", "半亩花田"],
        "vague_or_unknown": ["修丽可", "CPB", "赫莲娜", "海蓝之谜", "The Ordinary", "Drunk Elephant", "Aesop", "丸美", "隆力奇"],
        "awareness_rule": "年轻男性，熟悉男士品牌和超市常见品牌，知道大牌名字（女朋友用的），高端女性品牌和小众成分品牌不了解"
    },
    "persona_beauty_019": {
        # 方晓燕 42F 合肥 国企HR主管 16k T2
        "well_known": ["雅诗兰黛", "倩碧", "海蓝之谜", "兰蔻", "SK-II", "资生堂", "迪奥", "香奈儿", "欧莱雅", "玉兰油", "百雀羚", "自然堂", "大宝", "妮维雅"],
        "heard_of": ["赫莲娜", "CPB", "珀莱雅", "韩束", "薇诺娜", "丸美", "相宜本草", "理肤泉", "修丽可"],
        "vague_or_unknown": ["至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "Drunk Elephant", "理然", "溪木源", "肌司研"],
        "awareness_rule": "品牌忠诚的中年女性，非常熟悉雅诗兰黛集团和国际大牌，认识主流国货，新锐线上品牌完全不了解"
    },
    "persona_beauty_020": {
        # 唐小雨 25F 上海 外企市场专员 15k
        "well_known": ["SK-II", "黛珂", "资生堂", "娇韵诗", "兰蔻", "雅诗兰黛", "迪奥", "香奈儿", "欧莱雅", "倩碧", "CPB", "海蓝之谜", "珀莱雅", "薇诺娜", "自然堂"],
        "heard_of": ["修丽可", "理肤泉", "Drunk Elephant", "Aesop", "至本", "PMPM", "花西子", "完美日记", "百雀羚", "韩束", "HBN", "The Ordinary"],
        "vague_or_unknown": ["大宝", "隆力奇", "蛤蜊油", "友谊雪花膏", "温碧泉", "肌司研", "理然"],
        "awareness_rule": "海归背景，非常熟悉日系和国际品牌，会关注Cosme大赏，主流国货认识，下沉市场品牌不了解"
    },
    "persona_beauty_021": {
        # 马秀英 55F 涡阳县 超市收银员 3.5k T5
        "well_known": ["大宝", "百雀羚", "玉兰油", "妮维雅", "隆力奇", "自然堂", "蛤蜊油", "友谊雪花膏"],
        "heard_of": ["珀莱雅", "韩束", "欧莱雅", "相宜本草", "丸美", "欧诗漫"],
        "vague_or_unknown": ["兰蔻", "雅诗兰黛", "SK-II", "资生堂", "修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "CPB", "赫莲娜", "海蓝之谜", "薇诺娜"],
        "awareness_rule": "五线县城中年女性，只认超市货架上能看到的品牌，国际大牌和线上品牌基本不了解"
    },
    "persona_beauty_022": {
        # 韩磊 38M 芜湖 汽车销售经理 15k T3
        "well_known": ["妮维雅", "欧莱雅", "大宝", "SK-II", "兰蔻", "雅诗兰黛", "资生堂", "迪奥", "香奈儿", "玉兰油", "百雀羚", "自然堂"],
        "heard_of": ["珀莱雅", "韩束", "倩碧", "海蓝之谜", "薇诺娜", "丸美", "碧欧泉"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "CPB", "赫莲娜", "Drunk Elephant", "理然"],
        "awareness_rule": "送礼场景男性，非常熟悉商场专柜大牌（送礼用），认识超市品牌（自用），新锐品牌和成分品牌不了解"
    },
    "persona_beauty_023": {
        # 周小玲 28F 绵阳 小学语文老师 6k T3
        "well_known": ["珀莱雅", "薇诺娜", "至本", "相宜本草", "欧莱雅", "百雀羚", "自然堂", "大宝", "妮维雅", "玉兰油", "兰蔻", "雅诗兰黛", "SK-II", "韩束"],
        "heard_of": ["理肤泉", "雅漾", "花西子", "完美日记", "资生堂", "倩碧", "丸美", "半亩花田", "HBN", "PMPM"],
        "vague_or_unknown": ["修丽可", "CPB", "赫莲娜", "海蓝之谜", "The Ordinary", "Drunk Elephant", "Aesop", "理然"],
        "awareness_rule": "三线城市年轻教师，熟悉性价比国货和主流品牌，知道大牌名字但觉得贵，高端小众不了解"
    },
    "persona_beauty_024": {
        # 谢丽华 47F 无锡 私企财务总监 25k T2
        "well_known": ["赫莲娜", "修丽可", "资生堂", "CPB", "雅诗兰黛", "兰蔻", "SK-II", "海蓝之谜", "迪奥", "香奈儿", "欧莱雅", "倩碧", "玉兰油", "百雀羚", "自然堂"],
        "heard_of": ["Drunk Elephant", "La Mer", "薇诺娜", "珀莱雅", "韩束", "花西子", "丸美", "理肤泉", "雅漾"],
        "vague_or_unknown": ["至本", "PMPM", "完美日记", "The Ordinary", "HBN", "溪木源", "理然", "肌司研", "半亩花田"],
        "awareness_rule": "高收入抗老精英，非常熟悉高端抗老品牌线，主流品牌都认识，年轻人的新锐品牌不了解"
    },
    "persona_beauty_025": {
        # 林小杰 24M 梅州 理发店造型师 7k T4
        "well_known": ["欧莱雅", "妮维雅", "大宝", "自然堂", "百雀羚", "珀莱雅", "花西子", "完美日记", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["理然", "半亩花田", "亲爱男友", "韩束", "资生堂", "倩碧", "薇诺娜", "至本", "橘朵"],
        "vague_or_unknown": ["修丽可", "CPB", "赫莲娜", "海蓝之谜", "The Ordinary", "Drunk Elephant", "PMPM", "HBN", "Aesop"],
        "awareness_rule": "四线城市年轻男性造型师，熟悉抖音热门品牌和超市品牌，知道大牌名字，高端线和成分品牌不了解"
    },
    "persona_beauty_026": {
        # 沈佳宁 21F 北京 传媒大三 6k
        "well_known": ["兰蔻", "SK-II", "雅诗兰黛", "MAC", "迪奥", "欧莱雅", "花西子", "完美日记", "珀莱雅", "薇诺娜", "百雀羚", "自然堂", "橘朵"],
        "heard_of": ["修丽可", "资生堂", "倩碧", "海蓝之谜", "至本", "PMPM", "HBN", "3CE", "韩束", "半亩花田", "The Ordinary", "理肤泉"],
        "vague_or_unknown": ["CPB", "赫莲娜", "Drunk Elephant", "Aesop", "隆力奇", "蛤蜊油", "友谊雪花膏", "丸美"],
        "awareness_rule": "北京大学生，小红书重度用户，熟悉年轻人品牌和大牌，高端贵妇线只知道名字，老牌国货不了解"
    },
    "persona_beauty_027": {
        # 陆雨薇 23F 广州 药学院研一 3.5k
        "well_known": ["The Ordinary", "修丽可", "薇诺娜", "至本", "珀莱雅", "欧莱雅", "兰蔻", "雅诗兰黛", "SK-II", "理肤泉", "雅漾", "百雀羚", "自然堂"],
        "heard_of": ["HBN", "PMPM", "溪木源", "花西子", "完美日记", "资生堂", "倩碧", "海蓝之谜", "CPB", "Drunk Elephant", "韩束", "玉泽"],
        "vague_or_unknown": ["赫莲娜", "Aesop", "大宝", "隆力奇", "蛤蜊油", "友谊雪花膏", "丸美", "温碧泉", "理然"],
        "awareness_rule": "药学研究生，对成分和配方有专业认知，熟悉成分党品牌和药妆线，高端贵妇线了解有限，下沉市场品牌不了解"
    },
    "persona_beauty_028": {
        # 吴甜甜 19F 郑州 大一 1.8k
        "well_known": ["欧莱雅", "百雀羚", "大宝", "妮维雅", "自然堂", "珀莱雅", "花西子", "完美日记", "韩束", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["半亩花田", "肌司研", "酵色", "橘朵", "薇诺娜", "至本", "资生堂", "玉兰油", "丸美"],
        "vague_or_unknown": ["修丽可", "CPB", "赫莲娜", "海蓝之谜", "The Ordinary", "Drunk Elephant", "PMPM", "HBN", "Aesop", "理肤泉"],
        "awareness_rule": "小城市来的大一新生，预算极低，熟悉超市品牌和抖音热门平价品牌，知道大牌名字但买不起，小众成分品牌不了解"
    },
    "persona_beauty_029": {
        # 张浩然 22M 西安 大四计算机 2.2k
        "well_known": ["妮维雅", "欧莱雅", "大宝", "百雀羚", "自然堂", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["珀莱雅", "韩束", "花西子", "完美日记", "资生堂", "玉兰油", "薇诺娜"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "The Ordinary", "HBN", "CPB", "赫莲娜", "海蓝之谜", "Drunk Elephant", "理然", "亲爱男友", "Aesop"],
        "awareness_rule": "理工科直男，只认女友买的和超市能看到的品牌，护肤品品牌认知极少，只知道最主流的几个名字"
    },
    "persona_beauty_030": {
        # 罗小敏 30F 苏州 连锁餐饮店长 5.5k T2
        "well_known": ["珀莱雅", "半亩花田", "自然堂", "妮维雅", "百雀羚", "大宝", "欧莱雅", "韩束", "玉兰油", "兰蔻", "雅诗兰黛", "SK-II"],
        "heard_of": ["薇诺娜", "花西子", "完美日记", "丸美", "相宜本草", "资生堂", "倩碧", "温碧泉", "欧诗漫"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "The Ordinary", "HBN", "CPB", "赫莲娜", "海蓝之谜", "Drunk Elephant", "Aesop"],
        "awareness_rule": "精打细算型，熟悉拼多多和百亿补贴上的品牌，认识超市品牌和主流国货，知道大牌名字但觉得太贵，高端小众不了解"
    },
    "persona_beauty_031": {
        # 田小丽 26F 阜阳 全职宝妈/团购团长 4k T4
        "well_known": ["韩束", "珀莱雅", "自然堂", "百雀羚", "大宝", "妮维雅", "玉兰油", "欧莱雅", "温碧泉", "相宜本草"],
        "heard_of": ["兰蔻", "雅诗兰黛", "SK-II", "薇诺娜", "花西子", "完美日记", "丸美", "欧诗漫", "半亩花田"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "The Ordinary", "HBN", "CPB", "赫莲娜", "海蓝之谜", "Drunk Elephant", "资生堂", "Aesop"],
        "awareness_rule": "四线城市团购宝妈，非常熟悉团购渠道和超市品牌，知道大牌名字但没用过，线上新锐和高端品牌完全不了解"
    },
    "persona_beauty_032": {
        # 孙淑芬 62F 上海 退休国企会计 8.5k
        "well_known": ["雅诗兰黛", "资生堂", "SK-II", "兰蔻", "欧珀莱", "欧莱雅", "玉兰油", "百雀羚", "大宝", "自然堂", "妮维雅", "倩碧", "迪奥", "香奈儿"],
        "heard_of": ["海蓝之谜", "赫莲娜", "CPB", "珀莱雅", "韩束", "相宜本草", "薇诺娜", "丸美"],
        "vague_or_unknown": ["修丽可", "理肤泉", "至本", "PMPM", "花西子", "完美日记", "The Ordinary", "HBN", "Drunk Elephant", "Aesop", "理然", "溪木源"],
        "awareness_rule": "上海退休阿姨，非常熟悉百货专柜品牌和超市品牌，知道几个高端牌子，线上新锐和年轻人品牌完全不了解"
    },
}


def main():
    for fname, awareness in BRAND_AWARENESS.items():
        fpath = PERSONAS_DIR / f"{fname}.json"
        if not fpath.exists():
            print(f"SKIP {fname}: file not found")
            continue

        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)

        profile = data.get("profile", {})
        if "brand_awareness" in profile:
            print(f"SKIP {fname}: brand_awareness already exists")
            continue

        profile["brand_awareness"] = awareness
        data["profile"] = profile

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")

        print(f"OK   {fname}: added brand_awareness ({len(awareness['well_known'])}+{len(awareness['heard_of'])}+{len(awareness['vague_or_unknown'])} brands)")

    print("\nDone!")


if __name__ == "__main__":
    main()
