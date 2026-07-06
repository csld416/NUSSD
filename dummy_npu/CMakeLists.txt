cmake_minimum_required(VERSION 3.10)
project(dummy_npu CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(simplessd-dummy-npu dummy_npu_main.cc)
