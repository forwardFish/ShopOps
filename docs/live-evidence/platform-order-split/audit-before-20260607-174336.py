from pathlib import Path
import json, sys
sys.path.insert(0, str(Path('.').resolve()))
from scripts.split_platform_order_tables import FeishuClient, load_settings, _load_dotenv, audit_order_duplicates
_load_dotenv()
client = FeishuClient(load_settings())
target_ids = {
    '天猫':'tbl0gBiMcAKMCcwI',
    '抖音':'tblTbbFkEepZAGru',
    '拼多多':'tblFI9ZNPzrjR6Jm',
    '视频号':'tblFlMuPnVEn8qkw',
}
result = audit_order_duplicates(client, target_ids)
path = Path('docs/live-evidence/platform-order-split/duplicate-audit-before.json')
path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
