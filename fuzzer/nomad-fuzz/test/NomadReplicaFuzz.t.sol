// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";

import {ReplicaVulnerable} from "../src/ReplicaVulnerable.sol";

contract NomadReplicaFuzz is Test {
    /// 1) Fuzz the initializer payload itself (the “upgradeAndCall/init” parameters).
    /// Property: after initialize, an *unproven* message must NOT be processable.
    function testFuzz_initializerInputs_preventUnprovenProcess(
        bool useZeroRoot,
        bytes32 otherRoot,
        uint256 confirmAtTime,
        bytes memory message
    ) public {
        vm.warp(1_000_000); // make confirmAt <= now easy

        ReplicaVulnerable r = new ReplicaVulnerable(address(this));

        bytes32 root = useZeroRoot ? bytes32(0) : otherRoot;

        // Ensure "acceptableRoot(root)" can become true for whatever root we set.
        // This makes the fuzzer actually test the dangerous region of the state space.
        uint256 t = bound(confirmAtTime, 1, block.timestamp);

        r.initialize(root, t);

        // We do NOT call prove(). So messages[keccak256(message)] is still 0x00 (unproven).
        // In a correct system, process(message) must revert.
        vm.expectRevert();
        r.process(message);
        // This test FAILS (detects the bug) when:
        //   root == 0x00  AND  confirmAt[0x00] is acceptable,
        // because then acceptableRoot(messages[mh]) = acceptableRoot(0x00) is true.
    }

    /// 2) Targeted regression test: after each upgrade, enforce the same property.
    /// This models “we upgraded; now run adversarial checks”.
    function testFuzz_upgradeRegression_preventUnprovenProcess(
        bool useZeroRootAfterUpgrade,
        bytes32 newRootOther,
        uint256 newConfirmAt,
        bytes memory message
    ) public {
        vm.warp(1_000_000);

        ReplicaVulnerable r = new ReplicaVulnerable(address(this));

        // Start from a safe-ish deployed state (non-zero root).
        r.initialize(bytes32(uint256(123)), block.timestamp);

        // Fuzz the upgrade payload (this is where Nomad went wrong).
        bytes32 newRoot = useZeroRootAfterUpgrade ? bytes32(0) : newRootOther;
        uint256 t = bound(newConfirmAt, 1, block.timestamp);

        r.upgrade(newRoot, t);

        // Again: message is unproven => should revert.
        vm.expectRevert();
        r.process(message);
        // This test FAILS when upgrade set root == 0x00 with acceptable confirmAt.
    }
}

/// Optional but powerful: stateful invariant fuzzing.
/// Lets the fuzzer discover sequences like:
///   upgrade(0x00, acceptable) -> process(random msg) -> BUG
contract NomadReplicaInvariant is StdInvariant, Test {
    NomadHandler internal h;

    function setUp() public {
        vm.warp(1_000_000);
        h = new NomadHandler();
        targetContract(address(h));
    }

    function invariant_unprovenMessagesNeverProcess() public view {
        assertFalse(h.unprovenProcessSucceeded());
    }
}

contract NomadHandler {
    ReplicaVulnerable public r;
    bool public unprovenProcessSucceeded;

    constructor() {
        r = new ReplicaVulnerable(address(this));
        // Start from non-zero root.
        r.initialize(bytes32(uint256(1)), block.timestamp);
    }

    function upgrade(bool useZeroRoot, bytes32 otherRoot, uint256 confirmAtTime) external {
        bytes32 root = useZeroRoot ? bytes32(0) : otherRoot;

        // Avoid needing Test.bound(): clamp into [1, now]
        uint256 nowTs = block.timestamp;
        uint256 t = (nowTs == 0) ? 1 : (1 + (confirmAtTime % nowTs));

        r.upgrade(root, t);
    }

    function prove(bytes calldata message) external {
        // Mark message as proven under the current committedRoot (toy model).
        r.prove(message, r.committedRoot());
    }

    function process(bytes calldata message) external {
        bytes32 mh = keccak256(message);
        bool unproven = (r.messages(mh) == bytes32(0));

        if (unproven) {
            try r.process(message) {
                // If this ever succeeds for an unproven message, we found the bug.
                unprovenProcessSucceeded = true;
            } catch {}
        } else {
            // For proven messages, we don't care (it may succeed or fail depending on state).
            try r.process(message) {} catch {}
        }
    }
}


contract NomadReplicaInvariantNoHints is StdInvariant, Test {
    NomadHandlerNoHints internal h;

    function setUp() public {
        h = new NomadHandlerNoHints();
        targetContract(address(h));
    }

    function invariant_unprovenMessagesNeverProcess_noHints() public view {
        assertFalse(h.unprovenProcessSucceeded());
    }
}

contract NomadHandlerNoHints is Test {
    ReplicaVulnerable public r;
    bool public unprovenProcessSucceeded;

    constructor() {
        // start from a reasonable non-zero state
        vm.warp(1);
        r = new ReplicaVulnerable(address(this));
        r.initialize(bytes32(uint256(1)), block.timestamp);
    }

    // Generic: time is part of the environment, not a Nomad-specific hint.
    function warp(uint64 ts) external {
        vm.warp(uint256(ts));
    }

    // No hinting: root can be anything; confirmAt can be anything (uint64 is realistic for timestamps).
    function upgrade(bytes32 newRoot, uint64 newConfirmAt) external {
        r.upgrade(newRoot, uint256(newConfirmAt));
    }

    function prove(bytes calldata message) external {
        r.prove(message, r.committedRoot());
    }

    function process(bytes calldata message) external {
        bytes32 mh = keccak256(message);
        bool unproven = (r.messages(mh) == bytes32(0));

        if (unproven) {
            try r.process(message) {
                unprovenProcessSucceeded = true;
            } catch {}
        } else {
            try r.process(message) {} catch {}
        }
    }
}
