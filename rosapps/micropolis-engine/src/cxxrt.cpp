/* cxxrt.cpp -- the little of the C++ library the Micropolis engine needs,
 * so that it links against musl alone, with no libc++ in the box.
 *
 * The engine is compiled without exceptions or RTTI, with libc++'s
 * templates made inline (_LIBCPP_DISABLE_EXTERN_TEMPLATE); what still
 * names the library is here: std::string's members, to_string, new and
 * delete over malloc and free, and the aborts.  Only for the box's Linux
 * builds: elsewhere the system's C++ library is linked as usual.
 *
 * SPDX-License-Identifier: MIT
 */
#include <string>
#include <cstdio>
#include <cstdlib>

template class std::basic_string<char>;

namespace std {
inline namespace __1 {
std::string to_string(int v)
{
    char b[16];
    snprintf(b, sizeof b, "%d", v);
    return std::string(b);
}

[[noreturn]] void __libcpp_verbose_abort(const char *, ...) noexcept { abort(); }
}
}

void *operator new(size_t n)
{
    void *p = malloc(n ? n : 1);
    if (!p) {
        abort();
    }
    return p;
}
void *operator new[](size_t n) { return operator new(n); }
void operator delete(void *p) noexcept { free(p); }
void operator delete[](void *p) noexcept { free(p); }
void operator delete(void *p, size_t) noexcept { free(p); }
void operator delete[](void *p, size_t) noexcept { free(p); }

extern "C" void __cxa_pure_virtual() { abort(); }
