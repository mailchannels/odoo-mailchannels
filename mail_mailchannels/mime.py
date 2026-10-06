"""Convert Odoo's prepared MIME message; never infer new envelope recipients."""
import base64
import binascii
from email.utils import getaddresses


class InvalidMessage(ValueError):
    pass


def addresses(value):
    return [{'email': addr, **({'name': name} if name else {})}
            for name, addr in getaddresses([str(value or '')]) if addr]


def convert(message, envelope_from, recipients):
    for name in ('From', 'To', 'Cc', 'Bcc', 'Reply-To', 'Subject', 'Message-ID',
                 'References', 'In-Reply-To', 'List-Unsubscribe',
                 'List-Unsubscribe-Post', 'X-MailChannels-Transactional'):
        if len(message.get_all(name, [])) > 1:
            raise InvalidMessage('Duplicate message headers are not supported.')
    allowed = {addr.casefold(): addr for addr in recipients}
    if not allowed or len(allowed) > 1000:
        raise InvalidMessage('A message must have 1–1000 envelope recipients.')
    sender = addresses(message['From'])
    if len(sender) != 1:
        raise InvalidMessage('Exactly one From address is required.')
    grouped, seen = {}, set()
    for kind in ('to', 'cc'):
        items = []
        for item in addresses(message[kind]):
            address = item['email'].casefold()
            if address in allowed and address not in seen:
                items.append(item)
                seen.add(address)
        if items:
            grouped[kind] = items
    if 'to' not in grouped:
        raise InvalidMessage('No deliverable visible To address: API transport cannot preserve this MIME envelope.')
    hidden = [{'email': value} for key, value in allowed.items() if key not in seen]
    if hidden:
        grouped['bcc'] = hidden
    content, attachments, cids = [], [], set()
    for part in message.walk():
        for name in ('Content-Type', 'Content-Transfer-Encoding', 'Content-Disposition', 'Content-ID'):
            if len(part.get_all(name, [])) > 1:
                raise InvalidMessage('Duplicate MIME headers are not supported.')
        if part.defects or any(getattr(value, 'defects', ()) for _, value in part.items()):
            raise InvalidMessage('Malformed MIME message.')
        if part.is_multipart():
            if part.get_content_type() not in ('multipart/mixed', 'multipart/alternative', 'multipart/related'):
                raise InvalidMessage('Unsupported multipart message type.')
            continue
        encoding = str(part.get('Content-Transfer-Encoding', '')).strip().lower()
        if encoding not in ('', '7bit', '8bit', 'binary', 'quoted-printable', 'base64'):
            raise InvalidMessage('Unsupported content transfer encoding.')
        # Decode Base64 strictly ourselves: get_payload(decode=True) silently
        # repairs bad padding/characters. MIME line whitespace is permitted.
        if encoding == 'base64':
            try:
                encoded = part.get_payload().encode('ascii')
                encoded = encoded.translate(None, b' \t\r\n')
                data = base64.b64decode(encoded, validate=True)
            except (UnicodeError, ValueError, binascii.Error, AttributeError):
                raise InvalidMessage('Malformed content transfer encoding.') from None
        else:
            data = part.get_payload(decode=True)
        if part.defects:
            raise InvalidMessage('Malformed content transfer encoding.')
        if data is None:
            raise InvalidMessage('Undecodable message part.')
        kind, filename = part.get_content_type(), part.get_filename()
        disposition = part.get_content_disposition()
        cid = str(part['Content-ID'] or '').strip('<>')
        if kind in ('text/plain', 'text/html') and not filename and disposition != 'attachment' and not cid:
            try:
                value = data.decode(part.get_content_charset() or 'utf-8', errors='strict')
            except (UnicodeError, LookupError) as exc:
                raise InvalidMessage('Unsupported text encoding.') from exc
            if any(item['type'] == kind for item in content):
                raise InvalidMessage('Multiple body parts of the same type are not supported.')
            content.append({'type': kind, 'value': value})
        else:
            if not filename:
                raise InvalidMessage('An attachment filename is required.')
            attachment = {'filename': filename, 'type': kind, 'content': base64.b64encode(data).decode('ascii')}
            if cid:
                if cid in cids:
                    raise InvalidMessage('Duplicate inline attachment ID.')
                cids.add(cid)
                attachment['content_id'] = cid
            attachments.append(attachment)
    if not content:
        raise InvalidMessage('A text or HTML body is required.')
    # Deliberate allowlist: do not forward transport/authentication/internal headers.
    headers = {}
    for name in ('References', 'In-Reply-To', 'List-Unsubscribe', 'List-Unsubscribe-Post'):
        if message[name]:
            headers[name] = str(message[name])
    original_id = str(message['Message-ID'] or '')
    if not original_id:
        raise InvalidMessage('Odoo Message-ID is required for submission tracking.')
    references = headers.get('References', '').split()
    if original_id not in references:
        references.append(original_id)
    headers['References'] = ' '.join(references)
    classification = str(message['X-MailChannels-Transactional'] or 'true').lower()
    if classification not in ('true', 'false'):
        raise InvalidMessage('Invalid transactional classification.')
    payload = {'from': sender[0], 'envelope_from': {'email': envelope_from},
               'personalizations': [grouped], 'subject': str(message['Subject'] or ''),
               'content': content, 'headers': headers, 'transactional': classification == 'true'}
    if message['Reply-To']:
        reply = addresses(message['Reply-To'])
        if len(reply) != 1:
            raise InvalidMessage('Exactly one Reply-To is supported.')
        payload['reply_to'] = reply[0]
    if attachments:
        payload['attachments'] = attachments
    return payload
