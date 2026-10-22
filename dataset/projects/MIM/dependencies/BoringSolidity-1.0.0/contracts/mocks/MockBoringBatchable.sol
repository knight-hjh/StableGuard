// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;
import {BoringBatchable} from "../BoringBatchable.sol";
import {MockERC20} from "./MockERC20.sol";

// solhint-disable no-empty-blocks

contract MockBoringBatchable is MockERC20(10000), BoringBatchable {

}
