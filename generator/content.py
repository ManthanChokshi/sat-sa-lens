"""Realistic SOC content: rule names, sources, severity mixes and note builders."""
from __future__ import annotations

import numpy as np

# category -> (rule names, plausible sources, severity weights over
# critical/high/medium/low/info)
CATEGORY_LIBRARY: dict[str, dict] = {
    "initial_access": {
        "rules": [
            "External RDP login from new geography",
            "Successful VPN login without MFA",
            "Exploit attempt against public web server",
            "Suspicious OAuth consent grant",
            "Drive-by download from newly registered domain",
        ],
        "sources": ["ids", "siem", "firewall"],
        "sev": [0.10, 0.28, 0.37, 0.20, 0.05],
    },
    "execution": {
        "rules": [
            "Suspicious PowerShell EncodedCommand",
            "WMI process creation from Office document",
            "Script interpreter spawned by browser",
            "Unsigned binary executed from %TEMP%",
            "mshta.exe launching remote content",
        ],
        "sources": ["edr", "siem"],
        "sev": [0.08, 0.30, 0.38, 0.19, 0.05],
    },
    "persistence": {
        "rules": [
            "New service installed on domain controller",
            "Registry Run key modified",
            "Scheduled task created by non-admin user",
            "WMI event subscription created",
            "SSH authorized_keys modified on server",
        ],
        "sources": ["edr", "siem"],
        "sev": [0.07, 0.26, 0.42, 0.20, 0.05],
    },
    "privilege_escalation": {
        "rules": [
            "User added to Domain Admins",
            "Token impersonation detected",
            "sudo misconfiguration exploited",
            "UAC bypass via fodhelper",
            "Kernel driver load from user-writable path",
        ],
        "sources": ["edr", "siem"],
        "sev": [0.14, 0.34, 0.33, 0.15, 0.04],
    },
    "defense_evasion": {
        "rules": [
            "Windows Defender real-time protection disabled",
            "Security event log cleared",
            "Process hollowing detected",
            "Firewall rule deleted on endpoint",
            "EDR agent stopped unexpectedly",
        ],
        "sources": ["edr", "siem"],
        "sev": [0.12, 0.32, 0.36, 0.16, 0.04],
    },
    "credential_access": {
        "rules": [
            "Multiple failed logins - RDP",
            "LSASS memory access by unknown process",
            "Kerberoasting - service ticket burst",
            "Password spray against OWA",
            "Credential file accessed on jump host",
        ],
        "sources": ["edr", "siem", "ids"],
        "sev": [0.11, 0.31, 0.38, 0.16, 0.04],
    },
    "discovery": {
        "rules": [
            "Internal port scan from workstation",
            "AD enumeration via net group",
            "SMB share enumeration burst",
            "Cloud IAM inventory API sweep",
            "OT asset discovery scan on Level 2 network",
        ],
        "sources": ["ids", "siem", "ot_monitor"],
        "sev": [0.03, 0.18, 0.44, 0.29, 0.06],
    },
    "lateral_movement": {
        "rules": [
            "PsExec service created on remote host",
            "Pass-the-hash authentication pattern",
            "RDP chaining across three hosts",
            "WinRM session from non-admin workstation",
            "SMB admin share write to server",
        ],
        "sources": ["edr", "siem", "ids"],
        "sev": [0.13, 0.36, 0.34, 0.14, 0.03],
    },
    "collection": {
        "rules": [
            "Mass file read on finance share",
            "Archive created from sensitive directory",
            "Screen capture utility executed",
            "Database bulk export outside maintenance window",
            "Clipboard harvesting tool detected",
        ],
        "sources": ["edr", "siem"],
        "sev": [0.08, 0.28, 0.40, 0.20, 0.04],
    },
    "exfiltration": {
        "rules": [
            "Large outbound transfer to cloud storage",
            "DNS tunnelling pattern detected",
            "Unapproved SFTP upload from database server",
            "Data transfer to sanctioned-list IP",
            "Encrypted archive emailed externally",
        ],
        "sources": ["ids", "firewall", "siem"],
        "sev": [0.18, 0.37, 0.30, 0.13, 0.02],
    },
    "command_and_control": {
        "rules": [
            "Beaconing to known C2 infrastructure",
            "Long-lived TLS session to rare destination",
            "Cobalt Strike named pipe detected",
            "Tor exit node connection from server VLAN",
            "HTTP POST beacon with fixed interval",
        ],
        "sources": ["ids", "firewall", "edr"],
        "sev": [0.21, 0.39, 0.28, 0.10, 0.02],
    },
    "impact": {
        "rules": [
            "Ransomware canary file modified",
            "Shadow copies deleted",
            "OT setpoint changed outside change window",
            "Mass file rename with unknown extension",
            "Backup job deletion detected",
        ],
        "sources": ["edr", "ot_monitor", "siem"],
        "sev": [0.30, 0.34, 0.24, 0.10, 0.02],
    },
    "phishing": {
        "rules": [
            "Phishing URL clicked",
            "Credential harvesting page reported by user",
            "Malicious attachment quarantined",
            "Business email compromise - lookalike domain",
            "Mass phishing campaign against finance team",
        ],
        "sources": ["email_gateway", "siem"],
        "sev": [0.07, 0.29, 0.40, 0.20, 0.04],
    },
    "malware": {
        "rules": [
            "Trojan detected and quarantined",
            "Info-stealer signature match",
            "Cryptominer process on server",
            "Macro dropper blocked",
            "Known malicious hash executed",
        ],
        "sources": ["edr", "email_gateway", "siem"],
        "sev": [0.09, 0.30, 0.39, 0.18, 0.04],
    },
    "policy_violation": {
        "rules": [
            "USB mass storage device connected",
            "Unapproved remote access tool installed",
            "Cloud storage sync of corporate data",
            "Shared account used interactively",
            "Patch policy exception exceeded 30 days",
        ],
        "sources": ["edr", "siem", "firewall"],
        "sev": [0.01, 0.09, 0.32, 0.42, 0.16],
    },
}

CATEGORIES: list[str] = list(CATEGORY_LIBRARY)

# Categories that every sector should show; used to make negative space meaningful.
SECTOR_CATEGORY_BIAS: dict[str, dict[str, float]] = {
    "power": {"impact": 1.6, "discovery": 1.3, "policy_violation": 1.2},
    "banking": {"phishing": 2.1, "credential_access": 1.5, "collection": 1.3},
    "telecom": {"command_and_control": 1.5, "lateral_movement": 1.3, "discovery": 1.2},
    "oil_gas": {"impact": 1.7, "persistence": 1.2, "policy_violation": 1.2},
    "transport": {"impact": 1.4, "initial_access": 1.2, "policy_violation": 1.3},
}

ACTION_PHRASES = [
    "Host isolated via EDR and re-imaged",
    "Blocked the destination IP at the perimeter firewall",
    "Password reset forced and sessions revoked",
    "Escalated to Tier-3 for malware reverse engineering",
    "Quarantined the attachment and purged from all mailboxes",
    "Disabled the account pending HR review",
    "Killed the process tree and captured a memory image",
    "Raised a change request to patch the affected service",
    "Tuned the rule after confirming approved admin activity",
    "Added the hash to the EDR block list",
]

FINDING_PHRASES = [
    "Confirmed the activity matched an approved change window",
    "Traced the parent process to the approved deployment agent",
    "Correlated with the vulnerability scanner schedule",
    "Reviewed proxy logs and found no second-stage download",
    "Verified the user was travelling, confirmed by the manager",
    "Sandbox verdict was benign after full detonation",
    "Found the same binary on 14 peer hosts from the software catalogue",
    "No lateral movement observed in the following 24 hours",
    "Timeline shows the alert fired after the containment action",
    "Matched a known false-positive pattern documented in KB-2291",
]

TEMPLATE_NOTES = [
    "checked, false positive",
    "closed - no action needed",
    "reviewed. FP.",
    "not malicious, closing",
    "checked and closed",
]

SHALLOW_NOTES = [
    "looked into it, seems fine",
    "nothing unusual found during review",
    "as discussed with the team, closing this one",
    "no concerns after checking the usual places",
    "reviewed the alert and decided to close it",
    "handled as part of the daily queue",
]

TIERS = ["tier1", "tier2", "tier3", "ciso_office"]

ESCALATION_REASONS = [
    "Confirmed true positive on a critical asset",
    "Potential data exfiltration - needs IR lead",
    "Requires OT engineering sign-off before containment",
    "Scope larger than one host",
    "Regulatory notification may be required",
    "Needs malware reverse engineering",
]


def build_note(
    rng: np.random.Generator,
    hostname: str,
    username: str,
    ip: str,
    file_hash: str,
    severity: str,
    rule_name: str,
) -> str:
    """Build a varied, artefact-rich investigation note (healthy-analyst style)."""
    finding = FINDING_PHRASES[rng.integers(len(FINDING_PHRASES))]
    action = ACTION_PHRASES[rng.integers(len(ACTION_PHRASES))]
    shapes = [
        f"Triaged '{rule_name}' on host {hostname} ({ip}) for user {username}. "
        f"{finding}. SHA256 {file_hash[:32]}. {action}.",
        f"Alert on {hostname} raised for {username}. Source address {ip}. "
        f"{finding}. {action}. Severity assessed as {severity}.",
        f"Investigated {rule_name}. Artefacts: host={hostname}, user={username}, "
        f"src_ip={ip}, hash={file_hash[:24]}. {finding}. Action taken: {action}.",
        f"{finding} for the {rule_name} detection on {hostname}. Checked {ip} against "
        f"threat intel and pulled the process tree for {username}. {action}.",
        f"Reviewed telemetry for {hostname} between the first and last event. "
        f"User {username}, remote peer {ip}. {finding}. {action}.",
    ]
    return shapes[rng.integers(len(shapes))]
