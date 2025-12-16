// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Minimal model of the Nomad bug:
/// - `messages[msgHash]` defaults to 0x00 for unseen messages
/// - If an upgrade/initializer marks root 0x00 as acceptable, then
///   `acceptableRoot(messages[msgHash])` becomes true for any unseen message.
contract ReplicaVulnerable {
    address public owner;

    bytes32 public committedRoot;

    // "Root acceptance schedule" (simplified): root is acceptable if confirmAt[root] != 0
    // and confirmAt[root] <= block.timestamp.
    mapping(bytes32 => uint256) public confirmAt;

    // MessageHash -> Root that supposedly "proved" it.
    // Unseen: messages[hash] == 0x00
    mapping(bytes32 => bytes32) public messages;

    error NotOwner();
    error NotProven();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address _owner) {
        owner = _owner;
    }

    /// Represents initializer / upgradeAndCall payload in a simplified form.
    function initialize(bytes32 _committedRoot, uint256 _confirmAt) external onlyOwner {
        committedRoot = _committedRoot;
        confirmAt[_committedRoot] = _confirmAt;
    }

    /// Represents "upgrade regression": setting new root + acceptance time.
    function upgrade(bytes32 newRoot, uint256 newConfirmAt) external onlyOwner {
        committedRoot = newRoot;
        confirmAt[newRoot] = newConfirmAt;
    }

    function acceptableRoot(bytes32 root) public view returns (bool) {
        uint256 t = confirmAt[root];
        return t != 0 && t <= block.timestamp;
    }

    /// Vulnerable check: for an unseen message, messages[mh] == 0x00,
    /// so if acceptableRoot(0x00) becomes true, this passes.
    function process(bytes calldata message) external returns (bytes32 mh) {
        mh = keccak256(message);
        if (!acceptableRoot(messages[mh])) revert NotProven();

        // Mark processed (not important for the bug; just makes it stateful)
        messages[mh] = bytes32(uint256(1));
    }

    /// Optional "legit" path: set a message's root explicitly.
    function prove(bytes calldata message, bytes32 root) external onlyOwner {
        bytes32 mh = keccak256(message);
        messages[mh] = root;
    }
}
