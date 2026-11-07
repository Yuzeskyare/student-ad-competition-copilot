"""Bind AI's author-metadata judgment to the exact submitted copy."""
from datetime import datetime, timezone
from review_contract import timestamp


def validate_identity(record, input_sha256):
    if (not isinstance(record,dict) or record.get('kind')!='ad-copy-identity-review-v1'
            or record.get('input_sha256')!=input_sha256 or record.get('reviewer')!='ai'
            or type(record.get('has_creator_metadata')) is not bool
            or not isinstance(record.get('observation'),str) or not record['observation'].strip()
            or timestamp(record.get('reviewed_at'))>datetime.now(timezone.utc)):
        raise ValueError('AI identity judgment must bind the actual complete copy, observation and review time')
    return record['has_creator_metadata']


def validate_final_identity(root, manifest, input_sha256):
    from review_contract import bound_file, load
    record=load(bound_file(root,manifest.get('creator_identity_review')))
    if validate_identity(record,input_sha256):
        raise ValueError('AI identified prohibited entrant metadata in the final copy')
    return record
