"""Fail-closed Lotto 6/45 result publisher. No external Python dependencies."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from urllib import error, parse, request

BASE_URL = 'https://www.dhlottery.co.kr/lt645/'
LATEST_URL = BASE_URL + 'selectPstLt645Info.do'
HISTORY_URL = BASE_URL + 'selectPstLt645InfoNew.do'
FIRST_DRAW = date(2002, 12, 7)
KST = timezone(timedelta(hours=9))
MAX_RESPONSE = 512 * 1024
REQUIRED_KEYS = frozenset({
    'schema_version', 'round', 'draw_date', 'numbers', 'bonus',
    'verified', 'source', 'published_at',
})


class PipelineError(RuntimeError):
    pass


class _NoRedirects(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PipelineError('Official API redirected; refused to follow')


def fetch_official(url: str) -> dict:
    parsed = parse.urlsplit(url)
    if (parsed.scheme, parsed.hostname, parsed.port) != ('https', 'www.dhlottery.co.kr', None):
        raise PipelineError('Nonofficial endpoint rejected')
    opener = request.build_opener(_NoRedirects)
    req = request.Request(url, headers={
        'User-Agent': 'BokdeongiLottoResultVerifier/1.0',
        'Accept': 'application/json',
        'Referer': 'https://www.dhlottery.co.kr/lt645/result',
    })
    try:
        with opener.open(req, timeout=12) as response:
            ctype = response.headers.get('Content-Type', '')
            if response.status != 200 or 'application/json' not in ctype.lower():
                raise PipelineError('Invalid status or content type from official site')
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise PipelineError('Official result exceeds maximum size')
    except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
        raise PipelineError(f'Official site unavailable: {type(exc).__name__}') from exc
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise PipelineError('Official site returned invalid JSON') from exc
    if not isinstance(value, dict):
        raise PipelineError('Unexpected JSON response shape')
    return value


def extract_items(payload: object) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
        raise PipelineError('Missing official data object')
    values = payload['data'].get('list')
    if not isinstance(values, list) or not values or not all(isinstance(x, dict) for x in values):
        raise PipelineError('No announced draw results in official response')
    return values


def validate_round(record: dict, *, today: date | None = None) -> dict:
    if not isinstance(record, dict) or set(record) != REQUIRED_KEYS:
        raise PipelineError('Schema fields mismatch')
    round_no = record['round']
    if type(round_no) is not int or round_no < 1:
        raise PipelineError('Invalid draw round')
    try:
        expected_date = FIRST_DRAW + timedelta(days=(round_no - 1) * 7)
        recorded_date = date.fromisoformat(record['draw_date'])
    except (TypeError, ValueError, OverflowError) as exc:
        raise PipelineError('Invalid draw date') from exc
    if recorded_date != expected_date:
        raise PipelineError('Draw date does not match the round calendar')
    if recorded_date > (today or datetime.now(KST).date()):
        raise PipelineError('Future draw not eligible for publishing')
    nums = record['numbers']
    if not isinstance(nums, list) or len(nums) != 6 or any(type(n) is not int or n < 1 or n > 45 for n in nums):
        raise PipelineError('Invalid six winning numbers')
    if len(set(nums)) != 6 or nums != sorted(nums):
        raise PipelineError('Winning numbers must be unique and sorted')
    bonus = record['bonus']
    if type(bonus) is not int or bonus not in range(1, 46) or bonus in nums:
        raise PipelineError('Invalid bonus number')
    if record['schema_version'] != 1 or record['verified'] is not True or record['source'] != 'dhlottery':
        raise PipelineError('Only verified dhlottery schema v1 records accepted')
    try:
        stamp = datetime.fromisoformat(record['published_at'])
    except (ValueError, TypeError) as exc:
        raise PipelineError('Invalid published_at') from exc
    if stamp.tzinfo is None:
        raise PipelineError('Published time must include time zone')
    return record


def normalize_official(item: dict, *, published_at: str | None = None, today: date | None = None) -> dict:
    try:
        round_no = item['ltEpsd']
        raw_date = item['ltRflYmd']
        nums = [item[f'tm{i}WnNo'] for i in range(1, 7)]
        bonus = item['bnsWnNo']
        if not isinstance(raw_date, str) or len(raw_date) != 8 or not raw_date.isascii() or not raw_date.isdigit():
            raise ValueError('Bad official date')
        formatted_date = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}'
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError('Official response has missing or malformed draw fields') from exc
    record = {
        'schema_version': 1, 'round': round_no, 'draw_date': formatted_date,
        'numbers': nums, 'bonus': bonus, 'verified': True, 'source': 'dhlottery',
        'published_at': published_at or datetime.now(KST).isoformat(timespec='seconds'),
    }
    return validate_round(record, today=today)


def _equivalent(a: dict, b: dict) -> bool:
    return all(a.get(key) == b.get(key) for key in REQUIRED_KEYS - {'published_at'})


def official_consensus(*, fetch=fetch_official, today: date | None = None) -> dict:
    latest_items = extract_items(fetch(LATEST_URL))
    if len(latest_items) != 1:
        raise PipelineError('Latest endpoint must return exactly one draw')
    latest = normalize_official(latest_items[0], today=today)
    history_url = HISTORY_URL + '?' + parse.urlencode({'srchDir': 'center', 'srchLtEpsd': latest['round']})
    history_items = extract_items(fetch(history_url))
    matches = [x for x in history_items if type(x.get('ltEpsd')) is int and x['ltEpsd'] == latest['round']]
    if len(matches) != 1:
        raise PipelineError('Official historical lookup cannot verify latest round')
    history = normalize_official(matches[0], today=today)
    if not _equivalent(latest, history):
        raise PipelineError('Official endpoints disagree; publication blocked')
    return latest


def _load(path: Path, *, today: date | None = None) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise PipelineError(f'Existing result is unreadable: {path.name}') from exc
    return validate_round(payload, today=today)


def _atomic_save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pending_', suffix='.json', dir=path.parent)
    try:
        import os
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def publish(record: dict, site: Path, *, today: date | None = None, dry_run: bool = False) -> str:
    validate_round(record, today=today)
    latest_file = site / 'latest.json'
    round_file = site / 'rounds' / f"{record['round']}.json"
    existing_latest = _load(latest_file, today=today)
    existing_round = _load(round_file, today=today)
    if existing_latest is not None:
        old_round = existing_latest['round']
        if record['round'] < old_round:
            raise PipelineError('Round regression refused')
        if record['round'] > old_round + 1:
            raise PipelineError('Missing consecutive rounds; manual reconciliation required')
        if record['round'] == old_round and not _equivalent(existing_latest, record):
            raise PipelineError('Existing latest result conflicts with official data')
    elif existing_round is not None:
        raise PipelineError('Archive exists but latest pointer is missing; manual repair required')
    if existing_round is not None and not _equivalent(existing_round, record):
        raise PipelineError('Historical record conflicts with official data')
    if existing_latest is not None and existing_latest['round'] == record['round']:
        if existing_round is None:
            raise PipelineError('Missing round archive for current latest; manual repair required')
        return 'UNCHANGED'
    if dry_run:
        return 'WOULD_PUBLISH'
    # Round file first; latest last. Git commit publishes both files as one version.
    _atomic_save(round_file, record)
    _atomic_save(latest_file, record)
    return 'PUBLISHED'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', default=str(Path(__file__).resolve().parent / 'site'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        result = official_consensus()
        action = publish(result, Path(args.site), dry_run=args.dry_run)
        print(f'{action}: round={result["round"]} date={result["draw_date"]}')
    except PipelineError as exc:
        print(f'BLOCKED: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
