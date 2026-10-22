// SPDX-License-Identifier: UNLICENSED
pragma solidity >=0.8.0;

import "forge-std/Test.sol";
import "/libraries/BoringMath.sol";
import "forge-std/console2.sol";

contract BoringMathTest is Test {
    using BoringMath for uint256;
    using BoringMath32 for uint32;
    using BoringMath64 for uint64;
    using BoringMath112 for uint112;
    using BoringMath128 for uint128;
    using BoringMath224 for uint224;

    function setUp() public {}

    function testRevertOnUint32Overflow() public {
        uint256 a = type(uint32).max;
        uint32 b = a.to32();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to32();
    }

    function testRevertOnUint40Overflow() public {
        uint256 a = type(uint40).max;
        uint40 b = a.to40();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to40();
    }

    function testRevertOnUint64Overflow() public {
        uint256 a = type(uint64).max;
        uint64 b = a.to64();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to64();
    }

    function testRevertOnUint112Overflow() public {
        uint256 a = type(uint112).max;
        uint112 b = a.to112();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to112();
    }

    function testRevertOnUint128Overflow() public {
        uint256 a = type(uint128).max;
        uint128 b = a.to128();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to128();
    }

    function testRevertOnUint209Overflow() public {
        uint256 a = type(uint208).max;
        uint208 b = a.to208();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to208();
    }

    function testRevertOnUint216Overflow() public {
        uint256 a = type(uint216).max;
        uint216 b = a.to216();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to216();
    }

    function testRevertOnUint224Overflow() public {
        uint256 a = type(uint224).max;
        uint224 b = a.to224();
        assertEq(a, b);

        a++;
        vm.expectRevert(abi.encodeWithSelector(BoringMath.ErrOverflow.selector));
        b = a.to224();
    }

    /////////////////////////////////////////////////////////////////////
    /// BoringMath256
    /////////////////////////////////////////////////////////////////////

    function testMath256Add() public {
        uint256 a = type(uint256).max - 1;
        a = a.add(1);

        assertEq(a, type(uint256).max);
        vm.expectRevert();
        a.add(1);
    }

    function testMath256Sub() public {
        uint256 a = 1;
        a = a.sub(1);

        assertEq(a, 0);
        vm.expectRevert();
        a = a.sub(1);
    }

    function testMath256Mul() public {
        uint256 a = type(uint256).max;
        a = a.mul(1);
        assertEq(a, type(uint256).max);
        assertEq(a.mul(0), 0);

        vm.expectRevert();
        a = a.mul(2);
    }

    function testMath256Div() public {
        uint256 a = type(uint256).max;
        a = a.div(1);
        assertEq(a, type(uint256).max);

        vm.expectRevert();
        a = a.div(0);
    }

    /////////////////////////////////////////////////////////////////////
    /// BoringMath32
    /////////////////////////////////////////////////////////////////////

    function testMath32Add() public {
        uint32 a = type(uint32).max - 1;
        a = a.add(1);

        assertEq(a, type(uint32).max);
        vm.expectRevert();
        a.add(1);
    }

    function testMath32Sub() public {
        uint32 a = 1;
        a = a.sub(1);

        assertEq(a, 0);
        vm.expectRevert();
        a = a.sub(1);
    }

    function testMath32Mul() public {
        uint32 a = type(uint32).max;
        a = a.mul(1);
        assertEq(a, type(uint32).max);
        assertEq(a.mul(0), 0);

        vm.expectRevert();
        a = a.mul(2);
    }

    function testMath32Div() public {
        uint32 a = type(uint32).max;
        a = a.div(1);
        assertEq(a, type(uint32).max);

        vm.expectRevert();
        a = a.div(0);
    }

    /////////////////////////////////////////////////////////////////////
    /// BoringMath64
    /////////////////////////////////////////////////////////////////////
    function testMath64Add() public {
        uint64 a = type(uint64).max - 1;
        a = a.add(1);

        assertEq(a, type(uint64).max);
        vm.expectRevert();
        a.add(1);
    }

    function testMath64Sub() public {
        uint64 a = 1;
        a = a.sub(1);

        assertEq(a, 0);
        vm.expectRevert();
        a = a.sub(1);
    }

    function testMath64Mul() public {
        uint64 a = type(uint64).max;
        a = a.mul(1);
        assertEq(a, type(uint64).max);
        assertEq(a.mul(0), 0);

        vm.expectRevert();
        a = a.mul(2);
    }

    function testMath64Div() public {
        uint64 a = type(uint64).max;
        a = a.div(1);
        assertEq(a, type(uint64).max);

        vm.expectRevert();
        a = a.div(0);
    }

    /////////////////////////////////////////////////////////////////////
    /// BoringMath112
    /////////////////////////////////////////////////////////////////////
    function testMath112Add() public {
        uint112 a = type(uint112).max - 1;
        a = a.add(1);

        assertEq(a, type(uint112).max);
        vm.expectRevert();
        a.add(1);
    }

    function testMath112Sub() public {
        uint112 a = 1;
        a = a.sub(1);

        assertEq(a, 0);
        vm.expectRevert();
        a = a.sub(1);
    }

    function testMath112Mul() public {
        uint112 a = type(uint112).max;
        a = a.mul(1);
        assertEq(a, type(uint112).max);
        assertEq(a.mul(0), 0);

        vm.expectRevert();
        a = a.mul(2);
    }

    function testMath112Div() public {
        uint112 a = type(uint112).max;
        a = a.div(1);
        assertEq(a, type(uint112).max);

        vm.expectRevert();
        a = a.div(0);
    }

    /////////////////////////////////////////////////////////////////////
    /// BoringMath128
    /////////////////////////////////////////////////////////////////////
    function testMath128Add() public {
        uint128 a = type(uint128).max - 1;
        a = a.add(1);

        assertEq(a, type(uint128).max);
        vm.expectRevert();
        a.add(1);
    }

    function testMath128Sub() public {
        uint128 a = 1;
        a = a.sub(1);

        assertEq(a, 0);
        vm.expectRevert();
        a = a.sub(1);
    }

    function testMath128Mul() public {
        uint128 a = type(uint128).max;
        a = a.mul(1);
        assertEq(a, type(uint128).max);
        assertEq(a.mul(0), 0);

        vm.expectRevert();
        a = a.mul(2);
    }

    function testMath128Div() public {
        uint128 a = type(uint128).max;
        a = a.div(1);
        assertEq(a, type(uint128).max);

        vm.expectRevert();
        a = a.div(0);
    }

    /////////////////////////////////////////////////////////////////////
    /// BoringMath224
    /////////////////////////////////////////////////////////////////////
    function testMath224Add() public {
        uint224 a = type(uint224).max - 1;
        a = a.add(1);

        assertEq(a, type(uint224).max);
        vm.expectRevert();
        a.add(1);
    }

    function testMath224Sub() public {
        uint224 a = 1;
        a = a.sub(1);

        assertEq(a, 0);
        vm.expectRevert();
        a = a.sub(1);
    }

    function testMath224Mul() public {
        uint224 a = type(uint224).max;
        a = a.mul(1);
        assertEq(a, type(uint224).max);
        assertEq(a.mul(0), 0);

        vm.expectRevert();
        a = a.mul(2);
    }

    function testMath224Div() public {
        uint224 a = type(uint224).max;
        a = a.div(1);
        assertEq(a, type(uint224).max);

        vm.expectRevert();
        a = a.div(0);
    }
}
