from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import scripts.deploy_production as deploy_production


def write_keypair(tmp_path, dns_name: str, *, expires: datetime, key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_naive = expires.astimezone(timezone.utc).replace(tzinfo=None)
    not_before = min(now - timedelta(minutes=5), expires_naive - timedelta(minutes=1))
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(expires_naive)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns_name)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_dir = tmp_path / "deploy" / "certs"
    cert_dir.mkdir(parents=True)
    (cert_dir / "fullchain.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (cert_dir / "privkey.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return key


def test_deploy_preflight_accepts_valid_matching_domain_keypair(tmp_path, monkeypatch):
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    write_keypair(tmp_path, "paperplane.example", expires=expires)
    monkeypatch.setattr(deploy_production, "ROOT", tmp_path)

    result = deploy_production.validate_tls_certificate("paperplane.example")

    assert "valid through" in result


def test_deploy_preflight_rejects_localhost_certificate_for_production_domain(tmp_path, monkeypatch):
    expires = datetime.now(timezone.utc) + timedelta(days=30)
    write_keypair(tmp_path, "localhost", expires=expires)
    monkeypatch.setattr(deploy_production, "ROOT", tmp_path)

    with pytest.raises(deploy_production.DeploymentError, match="does not cover PAPERPLANE_DOMAIN"):
        deploy_production.validate_tls_certificate("paperplane.example")


def test_deploy_preflight_rejects_expired_certificate(tmp_path, monkeypatch):
    expires = datetime.now(timezone.utc) - timedelta(days=1)
    write_keypair(tmp_path, "paperplane.example", expires=expires)
    monkeypatch.setattr(deploy_production, "ROOT", tmp_path)

    with pytest.raises(deploy_production.DeploymentError, match="not currently valid"):
        deploy_production.validate_tls_certificate("paperplane.example")
